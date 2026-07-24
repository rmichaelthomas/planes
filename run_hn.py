import json

from interp import Interpreter, PlanesError
from parser import PlanesSyntaxError

STORIES = {
  1: {'title': 'Rust 2.0 released', 'score': 450},
  2: {'title': 'Why Go is fine', 'score': 300},
  3: {'title': 'Rewriting grep in Rust', 'score': 210},
  4: {'title': 'A rust postmortem', 'score': 150},
}

def stub(url):
    if 'topstories' in url:
        return json.dumps(list(STORIES.keys()))
    sid = int(url.split('/item/')[1].split('.json')[0])
    return json.dumps(STORIES[sid])

i = Interpreter(http=stub)
src = open('hn.planes').read()
try:
    out = i.run(src)
    print('OUTPUT:')
    for line in out:
        print(' ', line)
    print('\nEFFECTS:')
    for eff in i.effects:
        print(' ', eff)
    print('\nFILES:', list(i.fs.keys()))
except (PlanesError, PlanesSyntaxError) as e:
    print('ERROR:', e)
except Exception:
    import traceback
    traceback.print_exc()
