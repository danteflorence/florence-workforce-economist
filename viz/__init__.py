"""
Florence-themed Plotly chart helpers — reusable across internal, public, nurse surfaces.

Brand alignment:
  - Teal (#0ABAB5) for "with Florence" / positive
  - Navy (#101828) for "today" / baseline
  - Muted gray (#475467) for context
  - Playfair Display serif for titles, Inter for body
"""

FLORENCE_TEAL = "#0ABAB5"
FLORENCE_TEAL_DARK = "#067F7B"
FLORENCE_NAVY = "#101828"
FLORENCE_NAVY_SOFT = "#1A2A44"
FLORENCE_GRAY = "#F4F6F8"
FLORENCE_BORDER = "#E5E8EE"
FLORENCE_MUTED = "#475467"

# Sequential palette for choropleths (light → teal-dark)
TEAL_SCALE = [
    [0.0,  "#F4F6F8"],
    [0.2,  "#C7EFE4"],
    [0.4,  "#8FDFC8"],
    [0.6,  "#5DCDB0"],
    [0.8,  "#2BBC97"],
    [1.0,  "#067F7B"],
]

# Diverging palette (red → white → teal) for delta visualizations
DIVERGING = [
    [0.0, "#D14343"],
    [0.5, "#F4F6F8"],
    [1.0, "#067F7B"],
]
