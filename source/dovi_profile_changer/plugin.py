#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    dovi_profile_changer
"""
import logging
import os
import platform
from typing import Any, cast
from unmanic.libs.unplugins.settings import PluginSettings
from unmanic.libs.system import System
from .lib.ffmpeg import StreamMapper, Probe

logger = logging.getLogger("Unmanic.Plugin.DoviProfileChanger")


class Settings(PluginSettings):
    settings = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form_settings = {}

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

    probe = Probe(logger, allowed_mimetypes=["video"])
    if not probe.file(path):
        logger.info(f"File is not a video file: {path}")
        return data

    streams = probe.get("streams")
    for stream_info in streams:
        dovi = [data for data in (stream_info.get("side_data_list") or []) if data.get("side_data_type") == "DOVI configuration record"]

        if len(dovi) > 0:
            logger.info(f"File has DOVI metadata: {path}")
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

def bin_path() -> str:
    sys = platform.system().lower()
    return os.path.join(os.path.dirname(__file__), "bin", sys)

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
    settings = Settings(library_id=data.get("library_id"))

    add_to_path(bin_path())

    data["exec_command"] = []

    if data.get("step") is None:
        data["step"] = 1
    else:
        data["step"] += 1

    data["repeat"] = data["step"] < 4

    file_in = cast(str, data.get("file_in"))
    file_out = cast(str, data.get("file_out"))
    original_file_path = cast(str, data.get("original_file_path"))
    step = cast(int, data.get("step"))

    if step == 1:
        data["exec_command"] = [
            "ffmpeg",
            "-y",
            "-i",
            file_in,
            "-dn",
            "-c:v",
            "copy",
            "-vbsf",
            "hevc_mp4toannexb",
            "-f",
            "hevc",
            file_out
        ]

    elif step == 2:
        data["exec_command"] = [
            "dovi_tool",
            "-i",
            file_in,
            "-m",
            "2",
            "convert",
            "--discard",
            "-",
            "-o",
            file_out
        ]

    elif step == 3:
        data["exec_command"] = [
            "mp4box",
            "-add",
            f"'{file_in}':dvp=8.1:xps_inband:hdr=none",
            "-brand",
            "mp42isom",
            "-ab",
            "dby1",
            "-no-iod",
            "-enable",
            "1",
            file_out,
        ]

    elif step == 4:
        data["repeat"] = False

        data["exec_command"] = [
            "ffmpeg",
            "-i",
            file_in,
            "-i",
            original_file_path,
            "-map",
            "0:v",
            "-map",
            "1",
            "-c",
            "copy",
            file_out,
        ]

    # Command 1
    # ffmpeg -y -i 'in.mkv' -dn -c:v copy -vbsf hevc_mp4toannexb -f hevc original.hevc

    # Command 2
    # dovi_tool -i original.hevc -m 2 convert --discard - -o 'out.hevc'

    # Command 3
    # MP4Box -add 'out.hevc':dvp=8.1:xps_inband:hdr=none -brand mp42isom -ab dby1 -no-iod -enable 1 'out.mp4' -tmp '/path_to_tmp folder/'

    # Command 4
    # ffmpeg -i path_to_hevc.mp4 -i in.mp4 -map 0:v -map 1 -c copy output.mp4

    return data

def add_to_path(new_path):
    """Adds a directory to the PATH environment variable for the current session."""
    if not os.path.isdir(new_path):
        logger.warning(f"'{new_path}' is not a valid directory.")
        return

    # Get the current PATH
    current_path = os.environ.get('PATH', '')

    # Check if the path is already in PATH
    if new_path in current_path:
        logger.warning(f"'{new_path}' is already in PATH.")
        return

    # Add the new path to the beginning (recommended for precedence)
    os.environ['PATH'] = new_path + os.pathsep + current_path
    logger.info(f"Added '{new_path}' to PATH.")
