"""Serpentine keyboard traversal for the verified eight-column local layout.

Start at the top-left item. At a row edge move down, then reverse direction.
The session's duplicate detection remains the conservative end-of-list guard.
"""


class GridNavigation:
    def __init__(self, columns=8):
        if columns < 1:
            raise ValueError('列数必须为正整数')
        self.columns = columns
        self.reset()

    def reset(self):
        self.column = 0
        self.direction = 1

    def next_key(self):
        next_column = self.column + self.direction
        if 0 <= next_column < self.columns:
            self.column = next_column
            return 'd' if self.direction == 1 else 'a'
        self.direction *= -1
        return 's'
