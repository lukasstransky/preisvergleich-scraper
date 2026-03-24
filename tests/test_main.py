from unittest.mock import patch, MagicMock

from main import main


class TestMain:
    @patch("main.scrape_hofer")
    @patch("main.scrape_spar")
    @patch("main.scrape_billa")
    def test_main_calls_scrapers(self, mock_billa, mock_spar, mock_hofer, capsys):
        """Verify main() invokes the active scrapers and prints timing."""
        mock_spar.return_value = []

        main()

        # scrape_spar is the only active scraper (billa and hofer are commented out)
        mock_spar.assert_called_once()
        mock_billa.assert_not_called()
        mock_hofer.assert_not_called()

        captured = capsys.readouterr()
        assert "Starting Spar scraper..." in captured.out
        assert "Finished in" in captured.out

    @patch("main.scrape_spar")
    def test_main_timing_seconds(self, mock_spar, capsys):
        """Verify sub-60s timing output uses seconds."""
        mock_spar.return_value = []
        main()
        captured = capsys.readouterr()
        assert "seconds" in captured.out

    @patch("main.scrape_spar")
    @patch("main.time")
    def test_main_timing_minutes(self, mock_time, mock_spar, capsys):
        """Verify >=60s timing output uses minutes."""
        mock_spar.return_value = []
        # Simulate 120 seconds elapsed
        mock_time.time.side_effect = [0, 120]
        main()
        captured = capsys.readouterr()
        assert "minutes" in captured.out
