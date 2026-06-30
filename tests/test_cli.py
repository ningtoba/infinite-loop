"""Tests for CLI argument parsing via _create_parser."""

from omp_loop.cli import _create_parser


class TestParserCreation:
    """Test that the parser is created and has expected structure."""

    def test_parser_created(self):
        """_create_parser returns an ArgumentParser."""
        parser = _create_parser()
        assert parser is not None
        assert parser.prog == "omp-loop"

    def test_parser_no_introspection(self):
        """Parser without for_introspection includes help."""
        parser = _create_parser(for_introspection=False)
        actions = [a.option_strings for a in parser._actions if a.option_strings]
        assert any("--help" in opts or "-h" in opts for opts in actions)

    def test_parser_for_introspection(self):
        """Parser with for_introspection=True excludes help."""
        parser = _create_parser(for_introspection=True)
        # --help should not be present when add_help=False
        for action in parser._actions:
            if action.option_strings:
                assert "--help" not in action.option_strings


class TestVersionFlag:
    """Test --version parsing."""

    def test_version_flag_default(self):
        """--version defaults to False."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert not args.version

    def test_version_flag_set(self):
        """--version is set when passed."""
        parser = _create_parser()
        args = parser.parse_args(["--version"])
        assert args.version


class TestHelpFlag:
    """Test --help / -h handling."""

    def test_help_short_form(self):
        """-h is a recognised flag."""
        parser = _create_parser()
        # The long option is --help, short is -h
        assert any(
            "-h" in a.option_strings for a in parser._actions if a.option_strings
        )

    def test_help_long_form(self):
        """--help is a recognised flag."""
        parser = _create_parser()
        assert any(
            "--help" in a.option_strings for a in parser._actions if a.option_strings
        )


class TestGoalParsing:
    """Test --goal argument."""

    def test_goal_default_empty(self):
        """--goal defaults to empty string."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert args.goal == ""

    def test_goal_set(self):
        """--goal parses a string value."""
        parser = _create_parser()
        args = parser.parse_args(["--goal", "Fix all lint errors"])
        assert args.goal == "Fix all lint errors"

    def test_goal_with_special_chars(self):
        """--goal handles special characters."""
        parser = _create_parser()
        args = parser.parse_args(["--goal", "refactor auth module v2"])
        assert args.goal == "refactor auth module v2"


class TestMaxIterations:
    """Test --max-iterations argument."""

    def test_max_iterations_default(self):
        """--max-iterations defaults to 0 (unlimited)."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert args.max_iterations == 0

    def test_max_iterations_set(self):
        """--max-iterations parses an integer."""
        parser = _create_parser()
        args = parser.parse_args(["--max-iterations", "10"])
        assert args.max_iterations == 10

    def test_max_iterations_zero(self):
        """--max-iterations accepts 0."""
        parser = _create_parser()
        args = parser.parse_args(["--max-iterations", "0"])
        assert args.max_iterations == 0

    def test_max_iterations_large(self):
        """--max-iterations accepts large values."""
        parser = _create_parser()
        args = parser.parse_args(["--max-iterations", "999999"])
        assert args.max_iterations == 999999


class TestOtherFlags:
    """Spot-checks for other important flags."""

    def test_workers_default(self):
        """--workers defaults to 1."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert args.workers == 1

    def test_workers_set(self):
        """--workers parses an integer."""
        parser = _create_parser()
        args = parser.parse_args(["--workers", "4"])
        assert args.workers == 4

    def test_session_timeout_default(self):
        """--session-timeout defaults to 7200."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert args.session_timeout == 7200

    def test_color_default(self):
        """--color defaults to 'auto'."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert args.color == "auto"

    def test_color_choices(self):
        """--color accepts 'always' and 'never'."""
        parser = _create_parser()
        args = parser.parse_args(["--color", "always"])
        assert args.color == "always"
        args = parser.parse_args(["--color", "never"])
        assert args.color == "never"

    def test_git_flag_default(self):
        """--git defaults to False."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert not args.git

    def test_git_flag_set(self):
        """--git is True when passed."""
        parser = _create_parser()
        args = parser.parse_args(["--git"])
        assert args.git

    def test_run_flag_default(self):
        """--run defaults to False."""
        parser = _create_parser()
        args = parser.parse_args([])
        assert not args.run

    def test_run_flag_set(self):
        """--run is True when passed."""
        parser = _create_parser()
        args = parser.parse_args(["--run"])
        assert args.run

    def test_evolve_flag(self):
        """--evolve is supported."""
        parser = _create_parser()
        args = parser.parse_args(["--evolve"])
        assert args.evolve

    def test_convergence_stop_flag(self):
        """--convergence-stop is supported."""
        parser = _create_parser()
        args = parser.parse_args(["--convergence-stop"])
        assert args.convergence_stop
