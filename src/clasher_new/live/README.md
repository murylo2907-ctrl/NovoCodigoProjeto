# Cliente ao vivo (Frida + ADB)

A ponte entre um checkpoint treinado neste simulador e o jogo real. O simulador continua sendo a fonte da verdade: a observação montada aqui segue `environment.CREnv.observe()` (grid 8×32×18×15, mão, elixir, fila, elixir do inimigo, jogadas recentes), a decisão roda a cada 0,5 s e o banco de elixir segue `league_evaluation.EvaluationActor`.

| Arquivo | Papel |
| --- | --- |
| `live_hook.js` | roda dentro do processo do jogo (Frida); lê o estado e envia JSON a ~10 Hz |
| `live_client.py` | recebe o estado, monta a observação, consulta o checkpoint e chama o ADB |
| `adb_controller.py` | converte `(slot, y, x)` em um swipe da mão até o tile |
| `cards_live.json` | id de carta do jogo → nome interno do simulador (as 47 cartas implementadas) |
| `config.json` | pacote, dispositivo, retângulo da arena e posições da mão |
| `offsets.json` | offsets de memória — **por versão do jogo**, precisam ser preenchidos |

## Pré-requisitos

1. Emulador Android ARM64 com o jogo instalado (o pacote padrão em `config.json` é `com.supercell.clashroyale`; ajuste se o seu build usa outro).
2. `adb` no PATH e um dispositivo visível em `adb devices`.
3. `pip install frida` e o `frida-server` ARM64 correspondente rodando no emulador:
   ```bash
   adb push frida-server /data/local/tmp/frida-server
   adb shell "su -c 'chmod 755 /data/local/tmp/frida-server'"
   adb shell "su -c '/data/local/tmp/frida-server &'"
   ```
4. Um checkpoint `.zip` treinado aqui (`train_core.py` / `train_league.py`).

## Offsets: o único pedaço que não vem pronto

`offsets.json` é o mapa da memória daquela build do jogo. `live_hook.js` já traz a mecânica de leitura; os números vêm da sua versão. Fluxo de derivação:

1. Ache o módulo e o objeto global do estado:
   ```bash
   frida-trace -U -f com.supercell.clashroyale -i "libg.so!*"
   ```
2. Preencha `holder.offset` com o ponteiro global do estado de batalha (deixe `dereference: true` se o offset guarda um ponteiro; `false` se já é o objeto).
3. Rode `python live_client.py <modelo.zip> --probe` para despejar 0x200 bytes em volta do holder com os floats entre 0 e 10. Gaste elixir no jogo e veja qual offset cai de 10 para 0: esse é `elixir.offset`. O mesmo vale para `opponent_elixir` e `battle_time` (segundos).
4. Mão e fila: vetores de inteiros com os ids das cartas. Se a ordem vier invertida, ajuste no hook ou no `cards_live.json`.
5. Torres: array de 6 entradas com `hp` e `side`. `role_order` define a ordem dentro de cada lado.
6. Entidades: o hook assume o layout comum do motor Supercell — ponteiro para o array em `list_offset`, contagem em `count_offset`, `stride` e campos `id/card/side/x/y/hp`. Se a sua build usa hash map, adapte `readEntities()`; o resto da ponte não muda.

Ids de carta: `cards_live.json` usa os ids da API oficial (ex.: Knight `26000000`). Se o jogo guardar ids internos diferentes, edite o JSON — cartas desconhecidas são ignoradas e logadas.

## Calibração de tela

Em `config.json`:

- `arena`: frações da tela onde a arena começa/termina (o padrão assume 1080×2400, barra de elixir em cima e mão embaixo).
- `hand_x` / `hand_y`: centros das 4 cartas na mão, em fração da largura/altura.

O mapeamento usa `y=0` como o nosso lado (embaixo), igual ao simulador: `screen_y = bottom - (y+0.5)/32 × (bottom-top)`. O `ADBController` lê a resolução real com `adb shell wm size`, então só as frações importam.

## Rodar

```bash
cd src/clasher_new/live
python live_client.py ../../../../models/cycle6.zip --dry-run   # decide e loga, sem tocar na tela
python live_client.py ../../../../models/cycle6.zip             # loop completo
```

Logs no formato do bot: `[PLAY]`, `[IDLE]`, `[VISION]`. `--deterministic` troca amostragem por argmax. `--device local` usa o dispositivo Frida local; `--serial` escolhe o adb quando há mais de um.

## Limites conhecidos

- O deck do jogo precisa ser o mesmo do checkpoint: `Knight, MiniPekka, Arrows, Minions, Musketeer, Fireball, Giant, Archer`. O cliente avisa no primeiro frame se a mão não bate.
- Torres com `hp` ausente no hook são omitidas do grid; a máscara trata torre como viva.
- Ocupação por construções não é lida da memória; a máscara usa só a regra de metade/rio/torre destruída de `battle.can_place_troop`.
- Offsets quebram a cada atualização do jogo. O cliente toca na tela como um humano e não esconde o Frida do anticheat — teste em conta secundária.
