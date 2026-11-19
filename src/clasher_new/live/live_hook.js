// language: JavaScript, file: live_hook.js, target: Frida on Android ARM64
// Reads the live battle state out of the game process and emits JSON at ~10 Hz.
// Offsets are build-specific: live_client.py posts offsets.json into this script.
// If a field is not configured the script says so once and keeps polling the rest.

let CFG = null;
let holder = null;
let polling = null;
let lastError = null;

function report(message) {
    if (message !== lastError) {
        lastError = message;
        send({type: "error", message: message});
    }
}

function moduleBase() {
    const module = Process.findModuleByName(CFG.module);
    if (!module) {
        report("module not found: " + CFG.module);
        return null;
    }
    return module.base;
}

function holderPtr() {
    if (holder) return holder;
    const base = moduleBase();
    if (!base) return null;
    if (CFG.holder.offset === null || CFG.holder.offset === undefined) {
        report("holder.offset is not configured in offsets.json");
        return null;
    }
    holder = base.add(CFG.holder.offset);
    if (CFG.holder.dereference !== false) {
        holder = holder.readPointer();
    }
    return holder;
}

function readField(ptr, spec) {
    if (!spec || spec.offset === null || spec.offset === undefined) return null;
    const address = ptr.add(spec.offset);
    switch (spec.type) {
        case "float": return address.readFloat();
        case "int": return address.readS32();
        default: return address.readS32();
    }
}

function readArray(ptr, spec) {
    if (!spec || spec.offset === null || spec.offset === undefined) return null;
    const values = [];
    for (let i = 0; i < (spec.count || 0); i++) {
        values.push(readField(ptr.add(i * 4), {offset: spec.offset, type: spec.type}));
    }
    return values;
}

function readTowers(ptr) {
    const spec = CFG.towers;
    if (!spec || spec.offset === null || spec.offset === undefined) return null;
    const towers = [];
    for (let i = 0; i < (spec.count || 0); i++) {
        const entry = ptr.add(spec.offset + i * spec.stride);
        towers.push({
            hp: readField(entry, {offset: spec.fields.hp, type: "int"}),
            side: readField(entry, {offset: spec.fields.side, type: "int"}),
        });
    }
    return towers;
}

function readEntities(ptr) {
    const spec = CFG.entities;
    if (!spec || spec.list_offset === null || spec.count_offset === null || spec.stride === null) {
        return null;
    }
    const list = ptr.add(spec.list_offset).readPointer();
    const count = Math.max(0, Math.min(256, ptr.add(spec.count_offset).readS32()));
    const entities = [];
    for (let i = 0; i < count; i++) {
        const entry = list.add(i * spec.stride);
        entities.push({
            id: readField(entry, {offset: spec.fields.id, type: "int"}),
            card: readField(entry, {offset: spec.fields.card, type: "int"}),
            side: readField(entry, {offset: spec.fields.side, type: "int"}),
            x: readField(entry, {offset: spec.fields.x, type: "float"}),
            y: readField(entry, {offset: spec.fields.y, type: "float"}),
            hp: readField(entry, {offset: spec.fields.hp, type: "int"}),
        });
    }
    return entities;
}

function readState() {
    const ptr = holderPtr();
    if (!ptr) return null;
    const elixir = readField(ptr, CFG.elixir);
    if (elixir === null) {
        report("elixir.offset is not configured in offsets.json");
        return null;
    }
    return {
        type: "state",
        elixir: elixir,
        time: readField(ptr, CFG.battle_time),
        opponent_elixir: readField(ptr, CFG.opponent_elixir),
        hand: readArray(ptr, CFG.hand),
        queue: readArray(ptr, CFG.queue),
        towers: readTowers(ptr),
        entities: readEntities(ptr),
    };
}

function poll() {
    if (!CFG) return;
    try {
        const state = readState();
        if (state) send(state);
    } catch (error) {
        report("read failed: " + error);
    }
}

recv("config", function (message) {
    CFG = message.config;
    holder = null;
    send({type: "hello", module: CFG.module});
    if (polling) clearInterval(polling);
    polling = setInterval(poll, CFG.poll_ms || 100);
});

rpc.exports = {
    probe: function () {
        const ptr = holderPtr();
        if (!ptr) return "holder not resolved; fill holder.offset first";
        const dump = hexdump(ptr, {length: 0x200, header: true, ansi: false});
        const floats = [];
        for (let offset = 0; offset < 0x200; offset += 4) {
            try {
                const value = ptr.add(offset).readFloat();
                if (Number.isFinite(value) && value >= 0 && value <= 10) {
                    floats.push("0x" + offset.toString(16) + "=" + value.toFixed(2));
                }
            } catch (error) {
                // unmapped tail; skip
            }
        }
        return dump + "\nfloat candidates in 0..10:\n" + floats.join("  ");
    },
};
