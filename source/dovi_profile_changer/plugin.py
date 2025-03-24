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

def bin_path(tool: str) -> str:
    sys = platform.system().lower()
    ext = ".exe" if sys == "windows" else ""

    return os.path.join(os.path.dirname(__file__), "bin", sys, tool + ext)

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

    mp4box_path = bin_path("mp4box")
    dovi_tool_path = bin_path("dovi_tool")

    data["exec_command"] = []

    if data.get("step") is None:
        data["step"] = 1
    else:
        data["step"] += 1

    logger.info(f"Step {data['step']}")

    data["repeat"] = data["step"] < 5

    # Command 1
    # ffmpeg -y -i 'in.mkv' -dn -c:v copy -vbsf hevc_mp4toannexb -f hevc original.hevc

    # Command 2
    # dovi_tool -i original.hevc -m 2 convert --discard - -o 'out.hevc'

    # Command 3
    # MP4Box -add 'out.hevc':dvp=8.1:xps_inband:hdr=none -brand mp42isom -ab dby1 -no-iod -enable 1 'out.mp4' -tmp '/path_to_tmp folder/'

    # Command 4
    # ffmpeg -y -i 'path_to_hevc.mp4' -i 'path_to.mkv' -i 'path_to.srt' -loglevel error -stats -map "0:v?" -map "1:a:1" -map "2:s?" -dn -map_chapters 0 -movflags +faststart -c:v copy -c:a copy -c:s mov_text -metadata title="Movie Title (2023)" -metadata:s:v:0 handler_name="HEVC HDR10 / Dolby Vision" -metadata:s:a:0 handler_name="EAC3 5.1 Dolby Atmos" -metadata:s:s:0 language=ell -metadata:s:s:0 handler_name="MPEG-4 Timed Text" -strict experimental 'path_to_final.mp4'
    # ffmpeg -i path_to_hevc.mp4 -i in.mp4 -map 0:v -map 1 -c copy output.mp4

    return data
