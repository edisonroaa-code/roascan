# OCR fixture font

The generated English and Spanish documents use the same unmodified DejaVu Sans
font on every operating system. This prevents installed system fonts or Pillow's
fallback font from changing the input to the OCR regression tests.

Source (Matplotlib v3.10.7):
https://github.com/matplotlib/matplotlib/blob/v3.10.7/lib/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf

SHA-256:
`3fdf69cabf06049ea70a00b5919340e2ce1e6d02b0cc3c4b44fb6801bd1e0d22`

The accompanying `LICENSE_DEJAVU.txt` is copied verbatim from the same source:
https://github.com/matplotlib/matplotlib/blob/v3.10.7/lib/matplotlib/mpl-data/fonts/ttf/LICENSE_DEJAVU

These assets are included in source distributions for reproducible tests; they
are not part of the installed RoaScan runtime or its wheel.
