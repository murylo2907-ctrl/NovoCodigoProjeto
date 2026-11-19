"""Abre uma janela para você jogar contra um bot, ou assistir dois bots.

Exemplos:
    python meus_scripts/jogar.py human_style_strategy          # você (azul) x bot
    python meus_scripts/jogar.py split --assistir human        # bot x bot

Clique numa carta (ou tecle 1-4) e depois num tile para jogar. Espaço pausa,
Esc sai. Precisa de pygame e stable-baselines3 instalados (veja requirements.txt).
"""
import argparse
import time

import _comum

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("vermelho", help="nome de uma estratégia de strategies.py, ou um modelo .zip")
parser.add_argument("--assistir", dest="azul", help="assistir em vez de jogar: a estratégia (ou .zip) do lado azul")
parser.add_argument("--semente", type=int, default=int(time.time()))
parser.add_argument("--src", help="pasta src/clasher_new, se não for a padrão")
args = parser.parse_args()
_comum.preparar(args.src)

from play_vs_model import Game  # noqa: E402

Game(args.vermelho, args.semente, args.azul).run()
