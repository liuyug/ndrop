
import os.path
from io import BytesIO

from PIL import Image


IMAGES = {
    'back': 'BackTile.png',
    'pc': 'PcLogo.png',
    'android': 'AndroidLogo.png',
    'apple': 'AppleLogo.png',
    'darwin': 'AppleLogo.png',
    'blackberry': 'BlackberryLogo.png',
    'ip': 'IpLogo.png',
    'linux': 'LinuxLogo.png',
    'smartphone': 'SmartphoneLogo.png',
    'unknown': 'UnknownLogo.png',
    'windows': 'WindowsLogo.png',
    'windowsphone': 'WindowsPhoneLogo.png',
    'config': 'ConfigIcon.png',
    'openfolder': 'OpenFolderIcon.png',
    'hfs': 'hfs.png',
}


class NdropImage():
    @classmethod
    def get_os_image(cls, name):
        image_dir = os.path.join(os.path.dirname(__file__), 'image')

        back_path = os.path.join(image_dir, IMAGES['back'])
        back_im = Image.open(back_path)

        fore_path = os.path.join(
            image_dir,
            IMAGES.get(name.lower()) or IMAGES['unknown']
        )
        fore_im = Image.open(fore_path)

        image = Image.new("RGBA", fore_im.size)
        image.alpha_composite(back_im.resize(fore_im.size))
        image.alpha_composite(fore_im)
        return image

    @classmethod
    def get_os_tkimage(cls, name):
        from PIL import ImageTk
        return ImageTk.PhotoImage(cls.get_os_image(name))

    @classmethod
    def get_os_pngio(cls, name):
        img = cls.get_os_image(name)
        bio = BytesIO()
        img.save(bio, format='png')
        bio.seek(0)
        return bio

    @classmethod
    def get_image(cls, name, background=None):
        image_dir = os.path.join(os.path.dirname(__file__), 'image')

        fore_path = os.path.join(image_dir, IMAGES[name.lower()])
        fore_im = Image.open(fore_path)

        background = background or 'white'

        image = Image.new("RGBA", fore_im.size, color=background)
        image.alpha_composite(fore_im)
        return image

    @classmethod
    def get_tkimage(cls, name, background=None):
        from PIL import ImageTk
        return ImageTk.PhotoImage(cls.get_image(name, background=background))

    @classmethod
    def get_pngio(cls, name, background=None):
        img = cls.get_image(name, background=background)
        bio = BytesIO()
        img.save(bio, format='png')
        bio.seek(0)
        return bio
