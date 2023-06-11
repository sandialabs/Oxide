"""
Copyright 2023 National Technology & Engineering Solutions
of Sandia, LLC (NTESS). Under the terms of Contract DE-NA0003525 with NTESS,
the U.S. Government retains certain rights in this software.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

""" Wrapper for using ddisasm to extract basic block and instructions
"""

import os
import subprocess
import shutil
import logging
import time
import glob

from typing import Optional

SRC_VER = 0.1

NAME = "ddisasm"
logger = logging.getLogger(NAME)

# --------------------------- Tool N: DDISASM -----------------------------------------


def _cleanup_tempfiles():
    for file_path in glob.glob('scratch/ddisasm/binary/*'):
        try:
            os.remove(file_path)
        except IsADirectoryError:
            shutil.rmtree(file_path)


def _get_offset(vaddr, header_interface):
    if header_interface.type == "ELF":
        if header_interface.etype == "Shared object file":
            # If shared object, ddisasm does not rebase
            return vaddr
        # non-PIE, so use header info
        return header_interface.get_offset(vaddr)
    else:
        return vaddr


def _get_rva(vaddr, header_interface):
    return vaddr


def _scribe_version(output_map: dict) -> None:
    output_map['meta'] = {}
    output_map['meta']["tool_ver"] = "???"
    output_map['meta']["src_ver"] = SRC_VER
    output_map['meta']["name"] = "Ddisasm"


def _run_ddisasm(file_test, scratch_dir) -> Optional[str]:
    os.makedirs("scratch/ddisasm/", exist_ok=True)
    os.makedirs("scratch/ddisasm/binary/", exist_ok=True)

    # Mount temp file used in test to binary, store results in scratch dir under binary
    exe = "docker run --user=$(id -u):$(id -g) --rm -v {}:/binary -v {}:/scratch grammatech/ddisasm ddisasm".format(file_test, scratch_dir)
    cmd = "{} --json scratch/ddisasm/{}/cfg.json {} --debug-dir scratch/ddisasm/{} > /dev/null".format(
          exe, "binary", "binary", "binary")

    # FIXME:: put back to debug
    logger.info(cmd)
    with open(os.devnull, "w") as null:
        try:
            return subprocess.check_output(cmd, universal_newlines=True, shell=True, stderr=null)
        except subprocess.CalledProcessError as grepexc:
            logger.error("Ddisasm returned with non-zero exit code %s - %s",
                         grepexc.returncode,
                         grepexc.output)
            return None


def _record_data(output_map, data_list) -> None:
    """ Data found in analysis
    """
    # TODO:: parse data from output
    logging.debug(data_list)


def _extract_insn_facts(header_interface, exaustive_facts):
    """ Command to parse fact file for instructions
    """
    instruction_map = {}
    # use block information to pull out instructions found in CFG
    with open("scratch/ddisasm/binary/block_information.csv") as block_info_file:
        lines = block_info_file.read().split('\n')
        for line in lines:
            if line == "":
                continue

            # vaddr, size, end addr or last?
            block_info = line.split('\t')
            block_info = [int(item) for item in block_info]  # convert to list of ints

            i = _get_offset(block_info[0], header_interface)
            while i < _get_offset(block_info[2], header_interface):
                insn = exaustive_facts[i]
                file_offset = _get_offset(i, header_interface)
                instruction_map[file_offset] = insn['mneu']
                i += insn['size']

    return instruction_map


def _parse_exaustive(complete_facts_path, header_interface):
    instruction_map = {}
    # instruction_complete.facts is exaustive disassembly
    # instructions.facts is very stripped down and does not encompass most instructions
    # Utilizing exaustive + basic block information
    with open(complete_facts_path) as f:
        lines = f.read().split('\n')
        for line in lines:
            inst_comp_tokens = line.split('\t')
            if inst_comp_tokens[0] == '' or len(inst_comp_tokens) < 3:
                continue
            vaddr = int(inst_comp_tokens[0])
            # print("debugging, where is operands" + str(inst_comp_tokens))
            instruction_map[_get_offset(vaddr, header_interface)] = {'mneu': inst_comp_tokens[2] + ' ' + inst_comp_tokens[3], 'size': int(inst_comp_tokens[1])}

    return instruction_map


def _extract_block_facts(blk_info_path, header_interface):
    data_map = {}
    block_map = {}

    with open(blk_info_path, 'r') as f:
        print("block_facts", blk_info_path)
        lines = f.read().split('\n')
        for line in lines:
            block_tokens = line.split('\t')
            if block_tokens[0] == '' or len(block_tokens) < 3:
                continue

            vaddr = int(block_tokens[0])
            # print("debugging, where is operands" + str(inst_comp_tokens))
            block_map[_get_offset(vaddr, header_interface)] = {'size': int(line[1])}
    return data_map, block_map


def _populate_block_map(header_interface, block_map, insn_map, exhaustive_facts):
    print(exhaustive_facts)
    for bb in block_map:
        members = []

        insn = bb
        while bb < insn < bb + block_map[bb]['size']:
            members.append((insn, exhaustive_facts[_get_rva(insn, header_interface)]['mneu']))
            insn += exhaustive_facts[_get_rva(insn, header_interface)]['size']
        block_map[bb]['members'] = members
        del block_map[bb]['size']


def extract(file_test, header, scratch_dir):
    """ Runs instruction extraction from ghidraHEADLESS using a java language script
        Input -
            file_test - Sample using bap.run() which runs analyses
            header_interface (header) - header object using header utiility lib
    """
    output_map = {}
    output_map["meta"] = {}
    output_map["instructions"] = {}
    output_map["original_blocks"] = {}
    output_map["canon_blocks"] = {}

    _scribe_version(output_map)

    if not header.known_format:
        logger.info("File Sample is of unknown format, Ddisasm returning empty output.")
        return None

    start = time.time()

    # populate fact files
    ddisasm_stdout = _run_ddisasm(file_test, scratch_dir)
    if ddisasm_stdout is None:
        return None
    logging.info(ddisasm_stdout)

    end = time.time()
    output_map["meta"]["time"] = end - start

    # earlier versions used instructions_complete
    inst_facts = os.path.join(scratch_dir, "ddisasm", "binary", "instruction.facts")
    exaustive_facts = _parse_exaustive(inst_facts, header)
    output_map["instructions"] = _extract_insn_facts(header, exaustive_facts)

    block_facts = os.path.join(scratch_dir, "ddisasm", "binary", "block_information.csv")  # previous versions could use cfg.json
    # likely still can use cfg.json with more research
    res = _extract_block_facts(block_facts, header)

    if res is None:
        return None
    output_map['data'], output_map['original_blocks'] = res

    _populate_block_map(header, output_map['original_blocks'], output_map['instructions'], exaustive_facts)

    # FIXME:: replace references to relative scratch with api
    # FIXME:: replace general "binary" files with temp_name
    _cleanup_tempfiles()
    return output_map
