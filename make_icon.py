"""Draw a contact sheet icon at build time, with transparent outer corners."""
from pathlib import Path
from PIL import Image, ImageDraw
out = Path(__file__).parent/'assets'; out.mkdir(exist_ok=True)
im=Image.new('RGBA',(1024,1024)); d=ImageDraw.Draw(im)
d.rounded_rectangle((35,35,989,989),radius=150,fill='#eee9df',outline='#555555',width=12)
# A bordered sheet of nine landscape frames, like a photographic contact print.
for row in range(3):
    for col in range(3):
        x,y=100+col*280,110+row*265
        d.rectangle((x,y,x+260,y+210),fill='#333333')
        d.rectangle((x+12,y+12,x+248,y+165),fill=['#bccad0','#d6c7a9','#b6c3a5'][(col+row)%3])
        d.ellipse((x+180,y+30,x+210,y+60),fill='#f3ebd6')
        d.polygon([(x+12,y+165),(x+80,y+80),(x+145,y+140),(x+190,y+95),(x+248,y+165)],fill='#626e67')
        d.text((x+16,y+175),f'{row*3+col+1:02}',fill='#eeeeee',font_size=22)
im.save(out/'contact-sheet.png')
im.save(out/'contact-sheet.ico',sizes=[(16,16),(32,32),(48,48),(128,128),(256,256)])
im.save(out/'contact-sheet.icns')
