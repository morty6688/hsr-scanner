import unittest
from app.core.grid_navigation import GridNavigation


class NavigationTests(unittest.TestCase):
    def test_crosses_two_row_edges(self):
        nav = GridNavigation(8)
        self.assertEqual([nav.next_key() for _ in range(17)],
                         ['d'] * 7 + ['s'] + ['a'] * 7 + ['s', 'd'])

    def test_reset_replays_same_route(self):
        nav = GridNavigation(8)
        scanned = [nav.next_key() for _ in range(35)]
        nav.reset()
        self.assertEqual(scanned, [nav.next_key() for _ in range(35)])

    def test_visits_unique_cells(self):
        nav = GridNavigation(8)
        row, col = 0, 0
        visited = {(row, col)}
        for _ in range(31):
            key = nav.next_key()
            row += int(key == 's')
            col += int(key == 'd') - int(key == 'a')
            self.assertTrue(0 <= col < 8)
            self.assertNotIn((row, col), visited)
            visited.add((row, col))
        self.assertEqual(len(visited), 32)
