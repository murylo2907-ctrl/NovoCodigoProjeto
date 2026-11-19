"""Grava uma partida simulada em vídeo MP4, sem pygame (usa Pillow + ffmpeg).

Exemplos:
    python meus_scripts/gravar_partida.py human split
    python meus_scripts/gravar_partida.py human split --semente 31 --saida partida.mp4

Sem --semente, procura entre as sementes 1 a 40 uma partida decisiva, com coroas
dos dois lados. Precisa de Pillow instalado e do ffmpeg no PATH do sistema.
"""
import argparse
import random
import shutil
import subprocess
import sys
import time as _time
import types

import numpy as np

import _comum

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("azul", help="estratégia do lado azul (human, split, defensive, bridge, counterpush, punish)")
parser.add_argument("vermelho", help="estratégia do lado vermelho")
parser.add_argument("--semente", type=int, help="semente fixa; sem ela, procura uma partida decisiva")
parser.add_argument("--saida", default="partida.mp4", help="arquivo de saída (padrão: partida.mp4)")
parser.add_argument("--src", help="pasta src/clasher_new, se não for a padrão")
args = parser.parse_args()

if shutil.which("ffmpeg") is None:
    sys.exit("Não achei o ffmpeg no PATH. Instale o ffmpeg (ffmpeg.org) e tente de novo.")
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Falta a biblioteca Pillow. Rode: pip install pillow")

_comum.preparar(args.src)

import environment  # noqa: E402
from environment import CREnv  # noqa: E402
from battle import Building, Projectile  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

# O ambiente dorme 1/fps por tick quando há visualizador; anula isso.
environment.time = types.SimpleNamespace(sleep=lambda s: None, perf_counter=_time.perf_counter)

if args.azul not in STRATEGIES or args.vermelho not in STRATEGIES:
    sys.exit(f"Estratégias válidas: {', '.join(STRATEGIES)}")

TILE = 20
AX, AY = 20, 92
AW, AH = 18 * TILE, 32 * TILE
W, H = AW + 2 * AX, AY + AH + 96
_FONT = ImageFont.load_default
try:
    f_small = ImageFont.truetype("DejaVuSans.ttf", 9)
    f_mid = ImageFont.truetype("DejaVuSans.ttf", 12)
    f_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    f_huge = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
except OSError:
    f_small = f_mid = f_big = f_huge = _FONT()

BLUE, RED = (60, 110, 230), (220, 60, 60)
GRASS, GRASS2, RIVER, BRIDGE, BG = (122, 184, 92), (112, 174, 84), (80, 160, 220), (150, 110, 70), (24, 28, 40)


def w2s(x, y):
    return AX + x * TILE, AY + (32 - y) * TILE


def jogar(semente, gravador=None):
    random.seed(semente)
    np.random.seed(semente)
    env = CREnv(opponent_model=STRATEGIES[args.vermelho], visualize=False)
    env.reset(seed=semente)
    if gravador:
        gravador.battle = env.battle
        env.visualizer = gravador
    obs = env.observe(0)
    fim = False
    while not fim:
        obs, _, fim, _, _ = env.step(STRATEGIES[args.azul](obs))
    return env.battle


class Gravador:
    def __init__(self, caminho, fps=20, cada=2):
        self.cada, self.n, self.battle = cada, 0, None
        self.proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", caminho], stdin=subprocess.PIPE)

    def render_frame(self):
        self.n += 1
        if self.n % self.cada == 0:
            self.proc.stdin.write(self.desenhar().tobytes())

    def finalizar(self, segundos=3, fps=20):
        ultimo = self.desenhar()
        for _ in range(segundos * fps):
            self.proc.stdin.write(ultimo.tobytes())
        self.proc.stdin.close()
        self.proc.wait()

    def desenhar(self):
        b = self.battle
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        for ty in range(32):
            for tx in range(18):
                x0, y0 = AX + tx * TILE, AY + ty * TILE
                d.rectangle([x0, y0, x0 + TILE - 1, y0 + TILE - 1], fill=GRASS if (tx + ty) % 2 else GRASS2)
        ry = AY + 15 * TILE
        d.rectangle([AX, ry, AX + AW - 1, ry + 2 * TILE - 1], fill=RIVER)
        for bx in (2, 13):
            d.rectangle([AX + bx * TILE, ry, AX + (bx + 3) * TILE - 1, ry + 2 * TILE - 1], fill=BRIDGE)
        ents = sorted([e for e in b.entities.values() if e.is_alive],
                      key=lambda e: (not isinstance(e, Building), isinstance(e, Projectile)))
        for e in ents:
            sx, sy = w2s(e.position.x, e.position.y)
            col = BLUE if e.player == 0 else RED
            r = max(int(e.data.collision_radius * TILE), 4)
            if isinstance(e, Building):
                d.rectangle([sx - r, sy - r, sx + r, sy + r], fill=tuple(c // 2 + 60 for c in col),
                            outline=(20, 20, 20), width=2)
                d.text((sx, sy), str(int(max(e.hp, 0))), font=f_mid, fill="white", anchor="mm")
                continue
            if isinstance(e, Projectile):
                d.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], outline=col, width=2)
                continue
            if not getattr(e.data, "hp", 0):
                d.ellipse([sx - r, sy - r, sx + r, sy + r], outline=col, width=3)
                d.text((sx, sy), e.name, font=f_small, fill="white", anchor="mm")
                continue
            d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=col, outline=(15, 15, 15))
            frac = max(0.0, min(1.0, e.hp / e.data.hp)) if e.data.hp else 0
            bw = max(2 * r, 16)
            d.rectangle([sx - bw // 2, sy - r - 6, sx + bw // 2, sy - r - 3], fill=(20, 20, 20))
            d.rectangle([sx - bw // 2, sy - r - 6, sx - bw // 2 + int(bw * frac), sy - r - 3], fill=(90, 230, 90))
            d.text((sx, sy + r + 6), e.name, font=f_small, fill=(15, 15, 15), anchor="mm")
        p0, p1 = b.players
        t = b.time
        falta = max(180 - t, 0)
        relogio = f"{int(falta) // 60}:{int(falta) % 60:02d}" if t < 180 else f"PRORROGACAO +{int(t - 180)}s"
        mult = "x1" if t < 120 else ("x2" if t < 240 else "x3")
        d.text((W // 2, AY - 14), f"{relogio}   -   elixir {mult}", font=f_big, fill="white", anchor="mm")

        def lado(pl, col, rotulo, coroas, y):
            d.text((AX, y), rotulo, font=f_big, fill=col)
            d.text((W - AX, y), "O" * coroas + "." * (3 - coroas), font=f_big, fill=(255, 210, 60), anchor="ra")
            ey = y + 22
            d.rectangle([AX, ey, AX + AW, ey + 10], fill=(50, 50, 70))
            d.rectangle([AX, ey, AX + int(AW * pl.elixir / 10), ey + 10], fill=(200, 80, 220))
            d.text((AX, ey + 14), "mao: " + ", ".join(pl.cycle[:4]), font=f_small, fill=(200, 200, 210))

        lado(p1, RED, f"Vermelho - {args.vermelho}", p0.get_crown_count(), 2)
        lado(p0, BLUE, f"Azul - {args.azul}", p1.get_crown_count(), AY + AH + 10)
        if b.game_over:
            venc = "AZUL VENCEU" if b.winner == 0 else "VERMELHO VENCEU"
            col = BLUE if b.winner == 0 else RED
            d.rectangle([AX + 30, AY + AH // 2 - 30, AX + AW - 30, AY + AH // 2 + 30], fill=(255, 255, 255),
                        outline=col, width=4)
            d.text((W // 2, AY + AH // 2), venc, font=f_huge, fill=col, anchor="mm")
        return img


semente = args.semente
if semente is None:
    melhor = None
    for s in range(1, 41):
        b = jogar(s)
        cz, cv = b.players[1].get_crown_count(), b.players[0].get_crown_count()
        score = (min(cz, cv) > 0, max(cz, cv), -abs(b.time - 150))
        if melhor is None or score > melhor[0]:
            melhor = (score, s)
    semente = melhor[1]
    print(f"Semente escolhida: {semente}")

g = Gravador(args.saida)
b = jogar(semente, g)
g.finalizar()
venc = "azul" if b.winner == 0 else "vermelho"
print(f"Gravado: vencedor={venc}, coroas azul={b.players[1].get_crown_count()} "
      f"vermelho={b.players[0].get_crown_count()}, duracao={b.time:.0f}s -> {args.saida}")
