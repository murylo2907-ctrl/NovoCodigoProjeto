"""Live client: Frida reads the battle, a checkpoint decides, ADB plays the card.

    python live_client.py path/to/checkpoint.zip --dry-run   # decide and log, no ADB
    python live_client.py path/to/checkpoint.zip             # full loop

The observation layout is environment.CREnv.observe(); this client only swaps the
simulated BattleState for the state live_hook.js reads from game memory. Decision
cadence (0.5 s), banking and legality follow league_evaluation.EvaluationActor.

Setup is in README.md: frida-server on the emulator, offsets.json for the game
build, and the hand/arena rectangle in config.json.
"""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INVOCATION_CWD = Path.cwd()
os.chdir(ROOT)                       # card_utils opens gamedata.json relative to cwd
sys.path.insert(0, str(ROOT))

import numpy as np

from arena import TileGrid
from card_utils import Card
from environment import (CARD_SLOTS, CARD_TYPE_ID, DECISION_SECONDS, ENTITY_ID, FRAMES,
                         INITIAL_DECKS, OPPONENT_PLAYS, Bank)

from adb_controller import ADBController

TOWERS = {
    (0, "king"): (int(TileGrid.BLUE_KING_TOWER.x), int(TileGrid.BLUE_KING_TOWER.y)),
    (0, "left"): (int(TileGrid.BLUE_LEFT_TOWER.x), int(TileGrid.BLUE_LEFT_TOWER.y)),
    (0, "right"): (int(TileGrid.BLUE_RIGHT_TOWER.x), int(TileGrid.BLUE_RIGHT_TOWER.y)),
    (1, "king"): (int(TileGrid.RED_KING_TOWER.x), int(TileGrid.RED_KING_TOWER.y)),
    (1, "left"): (int(TileGrid.RED_LEFT_TOWER.x), int(TileGrid.RED_LEFT_TOWER.y)),
    (1, "right"): (int(TileGrid.RED_RIGHT_TOWER.x), int(TileGrid.RED_RIGHT_TOWER.y)),
}
MODEL_DECK = set(INITIAL_DECKS[0])


def load_cards():
    raw = json.loads((HERE / "cards_live.json").read_text(encoding="utf-8"))
    return {int(card_id): name for card_id, name in raw.items()}


def tower_hps(state, role_order):
    """Group the hook's tower entries by side and name them by memory order."""
    towers = {"own": {}, "enemy": {}}
    counts = {"own": 0, "enemy": 0}
    for entry in state.get("towers") or []:
        side = "enemy" if int(entry.get("side") or 0) else "own"
        index = counts[side]
        counts[side] += 1
        if index < len(role_order):
            towers[side][role_order[index]] = float(entry.get("hp") or 0)
    return towers


def entity_channels(name, hp, enemy):
    data = Card(name)
    return np.array([
        ENTITY_ID[name], CARD_TYPE_ID[data.type], 1 if enemy else 0,
        data.elixir, data.speed, int(data.is_air_unit),
        int(data.attack_ground), int(data.attack_air),
        np.log(hp) / 10 if hp > 0 else 0.0,
        hp / data.hp if data.hp else 0.0,
        data.hit_speed, data.range / 3, data.sight_range / 3,
        data.damage / 200, data.projectile_data.damage / 200,
    ], dtype=np.float32)


def build_frame(state, card_by_id, towers):
    """One (32, 18, 15) board frame from the live state, in our own view."""
    frame = np.zeros((32, 18, 15), dtype=np.float32)
    for entity in state.get("entities") or []:
        name = card_by_id.get(int(entity.get("card") or -1))
        if name is None or name not in ENTITY_ID:
            continue
        hp = float(entity.get("hp") or 0)
        if hp <= 0:
            continue
        x = int(min(max(float(entity.get("x") or 0), 0), 17))
        y = int(min(max(32 - float(entity.get("y") or 0), 0), 31))
        frame[y][x] = entity_channels(name, hp, int(entity.get("side") or 0) != 0)
    for (side, role), (x, y) in TOWERS.items():
        hp = (towers.get("own" if side == 0 else "enemy") or {}).get(role) or 0
        if hp <= 0:
            continue
        name = "KingTower" if role == "king" else "King_PrincessTowers"
        frame[y][x] = entity_channels(name, float(hp), side != 0)
    return frame


class LiveTracker:
    """Board history and the opponent's recent plays, the two stateful observations."""

    def __init__(self, card_by_id):
        self.card_by_id = card_by_id
        self.history = []
        self.seen = {}
        self.enemy_plays = []
        self.warned = set()

    def warn(self, message):
        if message not in self.warned:
            self.warned.add(message)
            print("[live] " + message, flush=True)

    def update(self, state, towers, now):
        frame = build_frame(state, self.card_by_id, towers)
        if not self.history:
            self.history.extend(frame.copy() for _ in range(FRAMES))
        self.history.append(frame)
        if len(self.history) > FRAMES:
            self.history.pop(0)
        self._track(state, now)
        return self.history

    def _track(self, state, now):
        current = set()
        for entity in state.get("entities") or []:
            if int(entity.get("side") or 0) != 1:
                continue
            name = self.card_by_id.get(int(entity.get("card") or -1))
            if name is None:
                continue
            key = entity.get("id")
            if key is None:
                key = (name, round(float(entity.get("x") or 0)), round(float(entity.get("y") or 0)))
            current.add(key)
            if key not in self.seen:
                x = float(entity.get("x") or 0)
                y = 32 - float(entity.get("y") or 0)
                self.enemy_plays.append((now, name, x, y))
            self.seen[key] = now
        for key in [k for k, seen_at in self.seen.items() if k not in current and now - seen_at > 5]:
            del self.seen[key]
        self.enemy_plays = self.enemy_plays[-OPPONENT_PLAYS:]

    def plays_array(self, now):
        plays = np.zeros((OPPONENT_PLAYS, 4), dtype=np.float32)
        for row, (landed_at, name, x, y) in enumerate(reversed(self.enemy_plays)):
            plays[row] = ENTITY_ID.get(name, 0), now - landed_at, x, y
        return plays


def live_legal_mask(elixir, hand_names, towers):
    """(4, 32, 18) legality for player 0's view, following battle.can_place_troop."""
    mask = np.zeros((4, 32, 18), dtype=np.int8)
    enemy = towers.get("enemy") or {}
    left_alive = (enemy.get("left") or 0) > 0
    right_alive = (enemy.get("right") or 0) > 0
    for slot, name in enumerate(hand_names[:CARD_SLOTS]):
        if name is None:
            continue
        card = Card(name)
        if elixir + 1e-6 < card.elixir:
            continue
        if card.type == "spell":
            mask[slot] = 1
            continue
        for y in range(21):                       # y >= 21 is never deployable
            for x in range(18):
                if (x, y) in TileGrid.RIVER_TILES:
                    continue
                if y <= 1 and (x <= 6 or x > 12):
                    continue
                if y >= 15 and ((x < 9 and left_alive) or (x >= 9 and right_alive)):
                    continue
                mask[slot][y][x] = 1
    return mask


def live_intruders(state):
    """Enemy troops in our half (sim y < 16), for the bank's interrupt rule."""
    intruders = set()
    for entity in state.get("entities") or []:
        if int(entity.get("side") or 0) != 1 or float(entity.get("hp") or 0) <= 0:
            continue
        if 32 - float(entity.get("y") or 0) < 16:
            key = entity.get("id")
            if key is None:
                key = (round(float(entity.get("x") or 0)), round(float(entity.get("y") or 0)))
            intruders.add(key)
    return intruders


def build_observation(history, hand_ids, elixir, now, queue_ids, opponent_elixir, plays):
    phase_end = next(end for end in (120, 180, 240, 300) if now < end or end == 300)
    return {
        "grid": np.stack(history),
        "hand": np.array(hand_ids, dtype=np.int32),
        "elixir": np.array([elixir], dtype=np.float32),
        "phase": (120, 180, 240, 300).index(phase_end),
        "time_till_next_phase": np.array([(phase_end - now) / 120.0], dtype=np.float32),
        "queue": np.array(queue_ids, dtype=np.int32),
        "opponent_elixir": np.array([opponent_elixir], dtype=np.float32),
        "decision_gap": np.zeros(1, dtype=np.float32),
        "opponent_plays": plays,
    }


class LiveActor:
    """A checkpoint with its own LSTM state and bank, as EvaluationActor runs it."""

    def __init__(self, model, deterministic=False):
        self.model = model
        self.deterministic = deterministic
        self.state = None
        self.bank = Bank()
        self.decided_at = 0.0
        self.decisions = 0

    def act(self, observation, mask, now, elixir, intruders):
        if self.bank.active(elixir, intruders) or not mask.any():
            return (0, 0, 0)
        self.decisions += 1
        gap = np.array([now - self.decided_at], dtype=np.float32)
        self.decided_at = now
        action, self.state = self.model.predict(
            dict(observation, legal_mask=mask, decision_gap=gap),
            state=self.state, deterministic=self.deterministic)
        slot, y, x = (int(value) for value in np.asarray(action).reshape(-1)[:3])
        return self.bank.resolve((slot, y, x), intruders)


def attach(device, package, spawn):
    if spawn:
        pid = device.spawn([package])
        return device.attach(pid), pid
    return device.attach(package), None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", help="PPO checkpoint (*.zip) trained by this repo")
    parser.add_argument("--dry-run", action="store_true", help="decide and log, never send ADB input")
    parser.add_argument("--deterministic", action="store_true", help="argmax actions instead of sampling")
    parser.add_argument("--serial", help="adb serial (defaults to config.json)")
    parser.add_argument("--device", help="frida device id: usb, local, or a device id")
    parser.add_argument("--probe", action="store_true", help="dump memory around the state holder and exit")
    args = parser.parse_args()

    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    offsets = json.loads((HERE / "offsets.json").read_text(encoding="utf-8"))
    role_order = offsets.get("towers", {}).get("role_order", ["king", "left", "right"])
    card_by_id = load_cards()

    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = INVOCATION_CWD / model_path
    from stable_baselines3 import PPO
    model = PPO.load(str(model_path), device="cpu")

    adb = None
    if not args.dry_run:
        adb = ADBController(serial=args.serial or config["adb"].get("serial"), config=config["adb"])

    import frida
    device_id = args.device or config.get("device", "usb")
    if device_id == "usb":
        device = frida.get_usb_device(timeout=5)
    elif device_id == "local":
        device = frida.get_local_device()
    else:
        device = frida.get_device(device_id, timeout=5)

    latest = {"state": None, "at": 0.0}
    counter = {"n": 0}
    lock = threading.Lock()

    def on_message(message, data):
        if message.get("type") != "send":
            print("[frida]", message.get("stack") or message, flush=True)
            return
        payload = message.get("payload") or {}
        if payload.get("type") == "state":
            with lock:
                latest["state"] = payload
                latest["at"] = time.time()
                counter["n"] += 1
        elif payload.get("type") == "hello":
            print("[live] hook loaded in", payload.get("module"), flush=True)
        elif payload.get("type") == "error":
            print("[live] hook:", payload.get("message"), flush=True)

    session, pid = attach(device, config["package"], config.get("spawn", True))
    script = session.create_script((HERE / "live_hook.js").read_text(encoding="utf-8"))
    script.on("message", on_message)
    script.load()
    script.post({"type": "config", "config": offsets})
    if pid is not None:
        device.resume(pid)

    if args.probe:
        time.sleep(1.5)
        print(script.exports_sync.probe())
        session.detach()
        return

    actor = LiveActor(model, deterministic=args.deterministic)
    tracker = LiveTracker(card_by_id)
    started = time.time()
    last_counter = 0
    last_vision = 0.0
    last_idle = 0.0
    print("[live] running; Ctrl+C to stop", flush=True)

    try:
        while True:
            time.sleep(DECISION_SECONDS)
            with lock:
                if counter["n"] == last_counter:
                    continue
                last_counter = counter["n"]
                state, state_at = latest["state"], latest["at"]
            if state is None or time.time() - state_at > 2.0:
                continue
            if state.get("hand") is None or state.get("elixir") is None:
                continue

            now = float(state["time"]) if state.get("time") is not None else time.time() - started
            hand_names = [card_by_id.get(int(card)) if card is not None else None
                          for card in state["hand"][:5]]
            hand_names += [None] * (5 - len(hand_names))
            if any(name is None for name in hand_names[:CARD_SLOTS]):
                tracker.warn("hand has cards missing from cards_live.json: " + repr(state["hand"][:CARD_SLOTS]))
            if any(name is not None and name not in MODEL_DECK for name in hand_names):
                tracker.warn("live deck differs from the checkpoint deck " + repr(list(INITIAL_DECKS[0])))

            elixir = float(state["elixir"])
            hand_ids = [ENTITY_ID.get(name, 0) for name in hand_names]
            queue_ids = [ENTITY_ID.get(card_by_id.get(int(card)), 0)
                         for card in (state.get("queue") or []) if card is not None][:3]
            queue_ids += [0] * (3 - len(queue_ids))
            towers = tower_hps(state, role_order)
            history = tracker.update(state, towers, now)
            mask = live_legal_mask(elixir, hand_names, towers)
            observation = build_observation(history, hand_ids, elixir, now, queue_ids,
                                            float(state.get("opponent_elixir") or 0.0),
                                            tracker.plays_array(now))
            intruders = lambda: live_intruders(state)
            slot, y, x = actor.act(observation, mask, now, elixir, intruders)

            if slot:
                card = hand_names[slot - 1] if 1 <= slot <= CARD_SLOTS else None
                target = None if adb is None else adb.play_card(slot - 1, y, x)
                print(f"[PLAY] slot={slot} card={card} tile=({y},{x}) "
                      f"{'dry' if target is None else 'px=' + str(target)}", flush=True)
            elif time.time() - last_idle >= 2.0:
                last_idle = time.time()
                print(f"[IDLE] elixir={elixir:.1f} hand={hand_names[:CARD_SLOTS]}", flush=True)

            if time.time() - last_vision >= config.get("log_vision_every", 2.0):
                last_vision = time.time()
                enemy = sum(1 for entity in state.get("entities") or []
                            if int(entity.get("side") or 0) == 1)
                print(f"[VISION] t={now:.0f}s elixir={elixir:.1f} enemy_units={enemy}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        session.detach()


if __name__ == "__main__":
    main()
