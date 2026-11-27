// APEDSK99 co-simulation, TI side: a peripheral card for ti99-headless
// (Machine(cards=[(this file, options)])). The card is the APEDSK99 8K RAM at
// >4000->5FFF, always visible (APEDSK99 does not decode the CRU). Every byte
// the TI writes there goes to firmware_server, which runs the real sketch
// and answers with the bytes it changed; the TI waits meanwhile, as with READY.
// The GAL signals a write only for A15 = 0: once per word (a MOVB is a
// read-modify-write of the whole word, so it signals once too).
//
// options: server (the firmware_server binary), sd, ftp (folders), eeprom (file),
//          log (file for the server's output)
// command({op: 'ram', addr, len}) -> the card RAM; command({op: 'writes'}) -> count
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const cp = require('child_process');

module.exports = function attach(ti, options) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apedsk99-'));
    const cmdPath = path.join(dir, 'cmd'), repPath = path.join(dir, 'rep');
    cp.execFileSync('mkfifo', [cmdPath, repPath]);
    const log = options.log ? fs.openSync(options.log, 'a') : 'ignore';
    const env = Object.assign({}, process.env, {SDROOT: options.sd, FTPROOT: options.ftp || options.sd,
        EEPROM_FILE: options.eeprom || path.join(dir, 'eeprom')});
    const child = cp.spawn(options.server, [cmdPath, repPath], {env, stdio: ['ignore', log, log]});
    const cmd = fs.openSync(cmdPath, 'w');
    const rep = fs.openSync(repPath, 'r');
    const ram = new Uint8Array(0x2000);
    let writes = 0;

    function readn(n) {
        const b = Buffer.alloc(n);
        let got = 0;
        while (got < n) {
            const r = fs.readSync(rep, b, got, n - got, null);
            if (r <= 0) throw new Error('APEDSK99 firmware_server ended');
            got += r;
        }
        return b;
    }
    function update() {                                    // apply one reply
        const h = readn(2), n = (h[0] << 8) | h[1];
        const b = readn(3 * n);
        for (let i = 0; i < n; i++) ram[((b[3 * i] << 8) | b[3 * i + 1]) & 0x1FFF] = b[3 * i + 2];
    }
    function writeWord(a, w) {
        ram[a] = w >> 8;
        ram[a + 1] = w & 0xFF;
        writes++;
        fs.writeSync(cmd, Buffer.from([0x57, a >> 8, a & 0xFF, w >> 8, w & 0xFF]));
        update();
    }
    update();                                              // setup(): the DSR loaded from the SD card

    const card = {
        getId: () => 'APEDSK99', getCruAddress: () => 0x1100,
        readCruBit: () => false, writeCruBit: () => {}, isEnabled: () => true,
        readMemoryMapped: (addr) => { const a = (addr - 0x4000) & 0x1FFE; return (ram[a] << 8) | ram[a + 1]; },
        writeMemoryMapped: (addr, w) => writeWord((addr - 0x4000) & 0x1FFE, w),
        getByte: (addr) => ram[(addr - 0x4000) & 0x1FFF],
    };
    ti.getMemory().registerPeripheralCard(card);
    return {
        command: (c) => c.op === 'ram' ? Array.from(ram.subarray(c.addr - 0x4000, c.addr - 0x4000 + (c.len || 1)))
                      : {writes},
        close: () => { try { fs.closeSync(cmd); fs.closeSync(rep); } catch (e) { /* gone */ } child.kill(); },
    };
};
