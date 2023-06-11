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

DESC = " This module uses the macho_parse package to extract features from the Mach-O header."
NAME = "macho"

import logging

from typing import Dict, Any

from interpret_macho import MachoRepr, UniversalRepr
from parse_macho import parse_macho
from core import api

logger = logging.getLogger(NAME)
logger.debug("init")

opts_doc = {}


def documentation() -> Dict[str, Any]:
    return {"description": DESC, "opts_doc": opts_doc, "set": False, "atomic": True}


def process(oid: str, opts: dict) -> bool:
    logger.debug("Processing oid %s", oid)
    src_type = api.get_field("src_type", oid, "type")
    if 'MACHO' in src_type:
        src = api.source(oid)
        data = api.get_field(src, oid, "data", {})
        if not data:
            logger.debug("Not able to process %s", oid)
            return False
        result = parse_macho(data, oid)
        result["header"] = MachoRepr(result)
        api.store(NAME, oid, result, opts)
        return True

    elif "OSX Universal Binary" in src_type:
        src = api.source(oid)
        data = api.get_field(src, oid, "data", {})
        if not data:
            logger.debug("Not able to process %s", oid)
            return False
        result = parse_macho(data, oid)
        result["header"] = UniversalRepr(result)
        api.store(NAME, oid, result, opts)
        return True

    else:
        return False
