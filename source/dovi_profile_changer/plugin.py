#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    dovi_profile_changer
"""
import logging
import os
import shutil
from typing import Any, cast
from unmanic.libs.unplugins.settings import PluginSettings
from unmanic.libs.system import System
from .lib.ffmpeg import StreamMapper, Probe
from github import Github

DOVI_TOOL_GITHUB="quietvoid/dovi_tool"
GPAC_DOWNLOAD_LINK="https://download.tsi.telecom-paristech.fr/gpac/new_builds/gpac_latest_head_{}.exe"

logger = logging.getLogger("Unmanic.Plugin.DoviProfileChanger")


class Settings(PluginSettings):
    settings = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form_settings = {}

class PluginStreamMapper(StreamMapper):
    settings: Settings
    probe: Probe

    def __init__(self, *, settings: Settings, probe: Probe):
        super().__init__(logger, ["video"])
        self.settings = settings
        self.probe = probe

    def test_stream_needs_processing(self, stream_info: dict):
        dovi = [data for data in (stream_info.get("side_data_list") or []) if data.get("side_data_type") == "DOVI configuration record"]
        return len(dovi) > 0

def on_library_management_file_test(data: dict[str, Any]):
    """
    Runner function - enables additional actions during the library management file tests.

    The 'data' object argument includes:
        path                            - String containing the full path to the file being tested.
        issues                          - List of currently found issues for not processing the file.
        add_file_to_pending_tasks       - Boolean, is the file currently marked to be added to the queue for processing.

    :param data:
    :return:
    """

    path = data.get("path")

    logger.info(f"Processing file: {path}")
    probe = Probe(logger, allowed_mimetypes=["video"])
    if not probe.file(path):
        logger.info(f"File is not a video file: {path}")
        return data

    settings = Settings(library_id=data.get("library_id"))
    mapper = PluginStreamMapper(settings=settings, probe=probe)

    if mapper.streams_need_processing():
        logger.info(f"File needs processing: {path}")
        data["add_file_to_pending_tasks"] = True

    return data


def on_postprocessor_task_results(data: dict):
    """
    Runner function - provides a means for additional postprocessor functions based on the task success.

    The 'data' object argument includes:
        task_processing_success         - Boolean, did all task processes complete successfully.
        file_move_processes_success     - Boolean, did all postprocessor movement tasks complete successfully.
        destination_files               - List containing all file paths created by postprocessor file movements.
        source_data                     - Dictionary containing data pertaining to the original source file.

    :param data:
    :return:
    """


    return data

def _get_platform(system_info: dict[str, Any]) -> tuple[str, str]:
    platform = cast(list, system_info.get("platform"))
    return (platform[0], platform[len(platform) - 1])

def _get_bin_path() -> str:
    return os.path.join(os.path.dirname(__file__), "bin")

def _ensure_dovi_tool(platform: tuple[str, str]) -> None:
    extension = ".exe" if platform[0] == "Windows" else ""
    path = os.path.join(_get_bin_path(), f"dovi_tool{extension}")

    if os.path.exists(path):
        return

    os.makedirs(_get_bin_path(), exist_ok=True)

    github = Github()
    repo = github.get_repo(DOVI_TOOL_GITHUB)
    latest_release = repo.get_latest_release()
    tag = latest_release.tag_name

    asset_file_suffix: str
    match platform[0]:
        case "Windows":
            asset_file_suffix = "pc-windows-msvc.zip"
        case "Linux":
            asset_file_suffix = "unknown-linux-musl.tar.gz"
        case "Darwin":
            asset_file_suffix = "universal-macOS.zip"
        case _:
            raise ValueError(f"Unsupported platform {platform[0]}")

    asset_file_name = f"dovi_tool-{tag}-{platform[1].lower()}-{asset_file_suffix}"

    logger.info(f"Searching for DOVI tool for platform {platform} on GitHub: {asset_file_name}")

    asset = next((asset for asset in latest_release.assets if asset.name == asset_file_name), None)
    if asset is None:
        logger.error(f"DOVI tool not found for platform {platform}")
        raise FileNotFoundError(f"DOVI tool not found for platform {platform}")

    logger.info(f"Found DOVI tool for platform {platform}: {asset.browser_download_url}")

    asset_dest_path = os.path.join(_get_bin_path(), asset_file_name)
    asset.download_asset(asset_dest_path)

    # Unzip the downloaded asset
    _unpack_asset(asset_dest_path, _get_bin_path())

def _unpack_asset(src: str, dest: str):
    shutil.unpack_archive(src, dest)

def _ensure_gpac(platform: tuple[str, str]) -> None:
    pass

def on_worker_process(data: dict[str, Any]):
    """
    Runner function - enables additional configured processing jobs during the worker stages of a task.

    The 'data' object argument includes:
        exec_command            - A command that Unmanic should execute. Can be empty.
        library_id              - Number, the library that the current task is associated with.
        command_progress_parser - A function that Unmanic can use to parse the STDOUT of the command to collect progress stats. Can be empty.
        file_in                 - The source file to be processed by the command.
        file_out                - The destination that the command should output (may be the same as the file_in if necessary).
        original_file_path      - The absolute path to the original file.
        repeat                  - Boolean, should this runner be executed again once completed with the same variables.

    :param data:
    :return:
    """

    system = System()
    system_info = system.info()
    platform = _get_platform(system_info)

    _ensure_dovi_tool(platform)
    _ensure_gpac(platform)

    settings = Settings(library_id=data.get("library_id"))


    return data
