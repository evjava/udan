import subprocess

from udan.core.api_exec_context import ExecContextAPI
from udan.core.api_forests import Item
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "shell"


def _preprocess_command(command):
    if command.startswith("fd"):
        return "fdfind" + command[3:]
    return command


@annotated(meta={"tool_type": "inserter", "output_type": "str"})
def shell_to_lines(ctx: ExecContextAPI | None = None, command: str = "", directory: str = ".") -> list[str]:
    """
    Executes command, returns lines
    """
    if ctx is not None:
        ctx.debug(f"Executing command: '{command}'")
    command = _preprocess_command(command)
    result = subprocess.run(command, cwd=directory, shell=True, text=True, capture_output=True)
    return result.stdout.splitlines()


@annotated(meta={"attribute_type": "simple"})
def shell_on(item: Item, command: str = "") -> str:
    """
    Executes command pattern on item, returns stdout

    If command contains $item, it is substituted with the item
    (assumed to be a path), otherwise item is appended to the command.

        >>> ls_files ., shell_on md5sum            # md5sum <item>
        >>> ls_files ., shell_on 'md5sum $item'    # md5sum <item>
    """
    if not command:
        raise ValueError("'shell_on' requires a command (e.g. shell_on md5sum)")
    pattern = command if "$item" in command else f"{command} $item"
    command = _preprocess_command(pattern.replace("$item", str(item)))
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    return result.stdout.strip()
