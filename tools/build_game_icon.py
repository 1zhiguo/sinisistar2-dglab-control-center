"""Frame the supplied artwork as a square SVG icon without altering its pixels."""
from pathlib import Path
import base64

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'website/dist/assets/icon.png'
    # Original art is 600x900. The lower 600x600 excludes the title at the top.
    payload=base64.b64encode(source.read_bytes()).decode('ascii')
    svg=('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" '
         'viewBox="0 300 600 600"><title>SiNiSistar2</title>'
         '<image x="0" y="0" width="600" height="900" '
         'href="data:image/png;base64,'+payload+'"/></svg>')
    target=ROOT/'website/dist/assets/game-icon.svg'
    target.write_bytes(svg.encode('utf-8'))
    print(target)

if __name__=='__main__':main()
