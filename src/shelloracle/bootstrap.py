from __future__ import annotations

import inspect
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tomlkit
from prompt_toolkit import print_formatted_text, prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import confirm

from shelloracle.providers import Provider, Setting, get_provider, list_providers

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


class UserError(Exception): ...


def print_info(info: str) -> None:
    print_formatted_text(FormattedText([("ansiblue", info)]))


def print_warning(warning: str) -> None:
    print_formatted_text(FormattedText([("ansiyellow", warning)]))


def print_error(error: str) -> None:
    print_formatted_text(FormattedText([("ansired", error)]))


def replace_home_with_tilde(path: Path) -> Path:
    relative_path = path.relative_to(Path.home())
    return Path("~") / relative_path


supported_shells = ("zsh", "bash", "fish")


def get_installed_shells() -> list[str]:
    return [shell for shell in supported_shells if shutil.which(shell)]


def get_bundled_script_path(shell: str) -> Path:
    shell_dir = Path(__file__).parent / "shell"
    if shell == "zsh":
        return shell_dir / "shelloracle.zsh"
    if shell == "fish":
        return shell_dir / "shelloracle.fish"
    return shell_dir / "shelloracle.bash"


def get_script_path(shell: str) -> Path:
    if shell == "zsh":
        return Path.home() / ".shelloracle.zsh"
    if shell == "fish":
        return Path.home() / ".shelloracle.fish"
    return Path.home() / ".shelloracle.bash"


def get_rc_path(shell: str) -> Path:
    if shell == "zsh":
        return Path.home() / ".zshrc"
    if shell == "fish":
        return Path.home() / ".config/fish/config.fish"
    return Path.home() / ".bashrc"


def write_script_home(shell: str) -> None:
    shelloracle = get_bundled_script_path(shell).read_bytes()
    destination = get_script_path(shell)
    destination.write_bytes(shelloracle)
    print_info(f"Successfully wrote key bindings to {replace_home_with_tilde(destination)}")


def update_rc(shell: str) -> None:
    rc_path = get_rc_path(shell)
    rc_path.touch(exist_ok=True)
    with rc_path.open("r") as file:
        rc_content = file.read()
    if shell == "fish":
        line = f"if test -f {get_script_path(shell)}; source {get_script_path(shell)}; end"
    else:
        shelloracle_script = get_script_path(shell)
        line = f"[ -f {shelloracle_script} ] && source {shelloracle_script}"
    if line not in rc_content:
        with rc_path.open("a") as file:
            file.write("\n")
            file.write(line)
    print_info(f"Successfully updated {replace_home_with_tilde(rc_path)}")


def get_settings(provider: type[Provider]) -> Iterator[tuple[str, Setting]]:
    settings = inspect.getmembers(provider, predicate=lambda p: isinstance(p, Setting))

    def correct_name_setting():
        for name, setting in settings:
            yield setting.name or name, setting

    yield from correct_name_setting()


def write_shelloracle_config(provider: type[Provider], settings: dict[str, Any], config_path: Path) -> None:
    config = tomlkit.document()

    shor_table = tomlkit.table()
    shor_table.add("provider", provider.name)
    config.add("shelloracle", shor_table)

    provider_table = tomlkit.table()
    config.add("provider", provider_table)

    provider_configuration_table = tomlkit.table()
    for setting, value in settings.items():
        provider_configuration_table.add(setting, value)
    provider_table.add(provider.name, provider_configuration_table)

    with config_path.open("w") as config_file:
        tomlkit.dump(config, config_file)


def install_keybindings() -> None:
    if not (shells := get_installed_shells()):
        print_warning(
            "Cannot install keybindings: no compatible shells found. " f"Supported shells: {' '.join(supported_shells)}"
        )
        return
    if confirm("Enable terminal keybindings and update rc?", suffix=" ([y]/n) ") is False:
        return
    for shell in shells:
        write_script_home(shell)
        update_rc(shell)


def user_configure_settings(provider: type[Provider]) -> dict[str, Any]:
    settings = {}
    for name, setting in get_settings(provider):
        user_input = prompt(f"{name}: ", default=str(setting.default))
        type_ = type(setting.default) if setting.default else str
        value = type_(user_input)  # type: ignore[operator]
        settings[name] = value
    return settings


def case_correct_user_input(user_input: str, options: Sequence[str]) -> str | None:
    for option in options:
        if user_input.lower() == option.lower():
            return option
    return None


def user_select_provider() -> type[Provider]:
    providers = list_providers()
    completer = WordCompleter(providers, ignore_case=True)
    user_selected_provider = prompt(f"Choose your LLM provider ({', '.join(providers)}): ", completer=completer)
    if (provider_name := case_correct_user_input(user_selected_provider, providers)) is None:
        msg = f"Invalid provider: {user_selected_provider or 'no input'}"
        raise UserError(msg)
    return get_provider(provider_name)


def bootstrap_shelloracle(config_path: Path) -> None:
    try:
        provider = user_select_provider()
        settings = user_configure_settings(provider)
    except UserError as e:
        print_error(str(e))
        return
    except KeyboardInterrupt:
        return
    write_shelloracle_config(provider, settings, config_path)
    install_keybindings()
