"""
Florence-themed Plotly chart helpers — reusable across internal, public, nurse surfaces.

Brand alignment:
  - Teal (#0BC5A0) for "with Florence" / positive
  - Navy (#0F1B2D) for "today" / baseline
  - Muted gray (#5B6675) for context
  - Newsreader serif for titles, Inter for body
"""

FLORENCE_TEAL = "#0BC5A0"
FLORENCE_TEAL_DARK = "#089478"
FLORENCE_NAVY = "#0F1B2D"
FLORENCE_NAVY_SOFT = "#1A2A44"
FLORENCE_GRAY = "#F4F6F8"
FLORENCE_BORDER = "#E5E8EE"
FLORENCE_MUTED = "#5B6675"

# Sequential palette for choropleths (light → teal-dark)
TEAL_SCALE = [
    [0.0,  "#F4F6F8"],
    [0.2,  "#C7EFE4"],
    [0.4,  "#8FDFC8"],
    [0.6,  "#5DCDB0"],
    [0.8,  "#2BBC97"],
    [1.0,  "#089478"],
]

# Diverging palette (red → white → teal) for delta visualizations
DIVERGING = [
    [0.0, "#D14343"],
    [0.5, "#F4F6F8"],
    [1.0, "#089478"],
]
