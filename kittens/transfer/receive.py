#!/usr/bin/env python
# License: GPLv3 Copyright: 2021, Kovid Goyal <kovid at kovidgoyal.net>

import os
import posixpath
from enum import auto
from typing import Dict, Iterator, List, Optional

from kitty.cli_stub import TransferCLIOptions
from kitty.fast_data_types import FILE_TRANSFER_CODE
from kitty.file_transmission import (
    Action, FileTransmissionCommand, NameReprEnum, encode_bypass
)

from ..tui.handler import Handler
from ..tui.loop import Loop, debug
from .utils import random_id

debug


class State(NameReprEnum):
    waiting_for_permission = auto()
    waiting_for_file_metadata = auto()
    transferring = auto()
    canceled = auto()


class File:

    def __init__(self, ftc: FileTransmissionCommand):
        self.expected_size = ftc.size
        self.ftype = ftc.ftype
        self.mtime = ftc.mtime
        self.spec_id = int(ftc.file_id)
        self.permissions = ftc.permissions
        self.remote_name = ftc.name
        self.remote_id = ftc.status
        self.remote_target = ftc.data.decode('utf-8')
        self.parent = ftc.parent
        self.local_name = ''


class TreeNode:

    def __init__(self, file: File, local_name: str, parent: Optional['TreeNode'] = None):
        self.entry = file
        self.entry.local_name = local_name
        self.children: List[TreeNode] = []
        self.parent = parent

    def add_child(self, file: File) -> 'TreeNode':
        c = TreeNode(file, os.path.join(self.entry.local_name, os.path.basename(file.remote_name)), self)
        self.children.append(c)
        return c


def make_tree(all_files: List[File], local_base: str) -> TreeNode:
    fid_map = {f.remote_id: f for f in all_files}
    node_map: Dict[str, TreeNode] = {}
    root_node = TreeNode(File(FileTransmissionCommand()), local_base)

    def ensure_parent(f: File) -> TreeNode:
        if not f.parent:
            return root_node
        parent = node_map.get(f.parent)
        if parent is None:
            fp = fid_map[f.parent]
            gp = ensure_parent(fp)
            parent = gp.add_child(fp)
        return parent

    for f in all_files:
        p = ensure_parent(f)
        p.add_child(f)
    return root_node


def files_for_receive(cli_opts: TransferCLIOptions, dest: str, files: List[File], remote_home: str, specs: List[str]) -> None:
    spec_map: Dict[int, List[File]] = {i: [] for i in range(len(specs))}
    for f in files:
        spec_map[f.spec_id].append(f)
    spec_paths = [spec_map[i][0].remote_name for i in range(len(specs))]
    if cli_opts.mode == 'mirror':
        try:
            common_path = posixpath.commonpath(spec_paths)
        except ValueError:
            common_path = ''
        home = remote_home.rstrip('/')
        if common_path and common_path.startswith(home + '/'):
            spec_paths = [posixpath.join('~', posixpath.relpath(x, home)) for x in spec_paths]
        for spec_id, files_for_spec in spec_map.items():
            spec = spec_paths[spec_id]
            tree = make_tree(files_for_spec, os.path.expanduser(spec))
    else:
        dest_is_dir = dest[-1] in (os.sep, os.altsep) or len(specs) > 1
        for spec_id, files_for_spec in spec_map.items():
            if dest_is_dir:
                dest_path = os.path.join(dest, posixpath.basename(files_for_spec[0].remote_name))
            else:
                dest_path = dest
            tree = make_tree(files_for_spec, os.path.expanduser(dest_path))
    tree


class Manager:

    def __init__(
        self, request_id: str, spec: List[str], dest: str,
        bypass: Optional[str] = None
    ):
        self.request_id = request_id
        self.spec = spec
        self.failed_specs: Dict[int, str] = {}
        self.spec_counts = dict.fromkeys(range(len(self.spec)), 0)
        self.dest = dest
        self.bypass = encode_bypass(request_id, bypass) if bypass else ''
        self.prefix = f'\x1b]{FILE_TRANSFER_CODE};id={self.request_id};'
        self.suffix = '\x1b\\'
        self.state = State.waiting_for_permission
        self.files: List[File] = []

    def start_transfer(self) -> Iterator[str]:
        yield FileTransmissionCommand(action=Action.send, bypass=self.bypass, size=len(self.spec)).serialize()
        for i, x in enumerate(self.spec):
            yield FileTransmissionCommand(action=Action.file, file_id=str(i), name=x).serialize()

    def on_file_transfer_response(self, ftc: FileTransmissionCommand) -> str:
        if self.state is State.waiting_for_permission:
            if ftc.action is Action.status:
                if ftc.status == 'OK':
                    self.state = State.waiting_for_file_metadata
                else:
                    return 'Permission for transfer denied'
            else:
                return f'Unexpected response from terminal: {ftc}'
        elif self.state is State.waiting_for_file_metadata:
            if ftc.action is Action.status:
                if ftc.file_id:
                    try:
                        fid = int(ftc.file_id)
                    except Exception:
                        return f'Unexpected response from terminal: {ftc}'
                    if fid < 0 or fid >= len(self.spec):
                        return f'Unexpected response from terminal: {ftc}'
                    self.failed_specs[fid] = ftc.status
                else:
                    if ftc.status == 'OK':
                        self.state == State.transferring
                        return ''
                    else:
                        return ftc.status
            elif ftc.action is Action.file:
                try:
                    fid = int(ftc.file_id)
                except Exception:
                    return f'Unexpected response from terminal: {ftc}'
                if fid < 0 or fid >= len(self.spec):
                    return f'Unexpected response from terminal: {ftc}'
                self.spec_counts[fid] += 1
                self.files.append(File(ftc))
            else:
                return f'Unexpected response from terminal: {ftc}'
        return ''


class Receive(Handler):
    use_alternate_screen = False

    def __init__(self, cli_opts: TransferCLIOptions, spec: List[str], dest: str = ''):
        self.cli_opts = cli_opts
        self.manager = Manager(random_id(), spec, dest, bypass=cli_opts.permissions_bypass)
        self.quit_after_write_code: Optional[int] = None

    def send_payload(self, payload: str) -> None:
        self.write(self.manager.prefix)
        self.write(payload)
        self.write(self.manager.suffix)

    def initialize(self) -> None:
        self.cmd.set_cursor_visible(False)
        self.print('Scanning files…')
        for x in self.manager.start_transfer():
            self.send_payload(x)

    def finalize(self) -> None:
        self.cmd.set_cursor_visible(True)

    def on_file_transfer_response(self, ftc: FileTransmissionCommand) -> None:
        if ftc.id != self.manager.request_id:
            return
        if ftc.status == 'CANCELED' and ftc.action is Action.status:
            self.quit_loop(1)
            return
        if self.quit_after_write_code is not None or self.manager.state is State.canceled:
            return
        transfer_started = self.manager.state is State.transferring
        err = self.manager.on_file_transfer_response(ftc)
        if err:
            self.print_err(err)
            self.quit_loop(1)
            return
        if not transfer_started and self.manager.state is State.transferring:
            if self.manager.failed_specs:
                self.print_err('Failed to process some sources')
                for spec_id, msg in self.manager.failed_specs.items():
                    spec = self.manager.spec[spec_id]
                    self.print(f'{spec}: {msg}')
                self.quit_loop(1)
                return
            if 0 in self.manager.spec_counts.values():
                self.print_err('No matches found for: ' + ', '.join(self.manager.spec[k] for k, v in self.manager.spec_counts.items() if v == 0))
                self.quit_loop(1)
                return
            self.print(f'Queueing transfer of {len(self.manager.files)} files(s)')

    def print_err(self, msg: str) -> None:
        self.cmd.styled(msg, fg='red')
        self.print()

    def on_term(self) -> None:
        if self.quit_after_write_code is not None:
            return
        self.print_err('Terminate requested, cancelling transfer, transferred files are in undefined state')
        self.abort_transfer(delay=2)

    def on_interrupt(self) -> None:
        if self.quit_after_write_code is not None:
            return
        if self.manager.state is State.canceled:
            self.print('Waiting for canceled acknowledgement from terminal, will abort in a few seconds if no response received')
            return
        self.print_err('Interrupt requested, cancelling transfer, transferred files are in undefined state')
        self.abort_transfer()

    def abort_transfer(self, delay: float = 5) -> None:
        self.send_payload(FileTransmissionCommand(action=Action.cancel).serialize())
        self.manager.state = State.canceled
        self.asyncio_loop.call_later(delay, self.quit_loop, 1)


def receive_main(cli_opts: TransferCLIOptions, args: List[str]) -> None:
    dest = ''
    if cli_opts.mode == 'mirror':
        if len(args) < 1:
            raise SystemExit('Must specify at least one file to transfer')
        spec = list(args)
    else:
        if len(args) < 2:
            raise SystemExit('Must specify at least one source and a destination file to transfer')
        spec, dest = args[:-1], args[-1]

    loop = Loop()
    handler = Receive(cli_opts, spec, dest)
    loop.loop(handler)
