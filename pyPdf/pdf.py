# -*- coding: utf-8 -*-
#
# vim: sw=4:expandtab:foldmethod=marker
#
# Copyright (c) 2006, Mathieu Fenniak
# Copyright (c) 2007, Ashish Kulkarni <kulkarni.ashish@gmail.com>
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


"""
A pure-Python PDF library with very minimal capabilities.  It was designed to
be able to split and merge PDF files by page, and that's about all it can do.
It may be a solid base for future PDF file work in Python.
"""
__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"

import math
import struct
from sys import version_info
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import filters
import utils
import warnings
from generic import *
from utils import readNonWhitespace, readUntilWhitespace, ConvertFunctionsToVirtualList

if version_info < ( 2, 4 ):
   from sets import ImmutableSet as frozenset

if version_info < ( 2, 5 ):
    from md5 import md5
else:
    from hashlib import md5

##
# This class supports writing PDF files out, given pages produced by another
# class (typically {@link #PdfFileReader PdfFileReader}).
class PdfFileWriter(object):
    def __init__(self):
        self._header = "%PDF-1.3"
        self._objects = []  # array of indirect objects

        # The root of our page tree node.
        pages = DictionaryObject()
        pages.update({
                NameObject("/Type"): NameObject("/Pages"),
                NameObject("/Count"): NumberObject(0),
                NameObject("/Kids"): ArrayObject(),
                })
        self._pages = self._addObject(pages)

        # info object
        info = DictionaryObject()
        info.update({
                NameObject("/Producer"): createStringObject(u"Python PDF Library - http://pybrary.net/pyPdf/")
                })
        self._info = self._addObject(info)

        # root object
        root = DictionaryObject()
        root.update({
            NameObject("/Type"): NameObject("/Catalog"),
            NameObject("/Pages"): self._pages,
            })
        self._root = self._addObject(root)

    def _addObject(self, obj):
        self._objects.append(obj)
        return IndirectObject(len(self._objects), 0, self)

    def getObject(self, ido):
        if ido.pdf != self:
            raise ValueError("pdf must be self")
        return self._objects[ido.idnum - 1]

    ##
    # Common method for inserting or adding a page to this PDF file.
    #
    # @param page The page to add to the document.  This argument should be
    #             an instance of {@link #PageObject PageObject}.
    # @param action The function which will insert the page in the dictionnary.
    #               Takes: page list, page to add.
    def _addPage(self, page, action):
        assert page["/Type"] == "/Page"
        page[NameObject("/Parent")] = self._pages
        page = self._addObject(page)
        pages = self.getObject(self._pages)
        action(pages["/Kids"], page)
        pages[NameObject("/Count")] = NumberObject(pages["/Count"] + 1)

    ##
    # Adds a page to this PDF file.  The page is usually acquired from a
    # {@link #PdfFileReader PdfFileReader} instance.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    #
    # @param page The page to add to the document.  This argument should be
    #             an instance of {@link #PageObject PageObject}.
    def addPage(self, page):
        self._addPage(page, list.append)

    ##
    # Writes the collection of pages added to this object out as a PDF file.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    # @param stream An object to write the file to.  The object must support
    # the write method, and the tell method, similar to a file object.
    def write(self, stream):
        import struct

        externalReferenceMap = {}

        # PDF objects sometimes have circular references to their /Page objects
        # inside their object tree (for example, annotations).  Those will be
        # indirect references to objects that we've recreated in this PDF.  To
        # address this problem, PageObject's store their original object
        # reference number, and we add it to the external reference map before
        # we sweep for indirect references.  This forces self-page-referencing
        # trees to reference the correct new object location, rather than
        # copying in a new copy of the page object.
        for objIndex in xrange(len(self._objects)):
            obj = self._objects[objIndex]
            if isinstance(obj, PageObject) and obj.indirectRef != None:
                data = obj.indirectRef
                if not externalReferenceMap.has_key(data.pdf):
                    externalReferenceMap[data.pdf] = {}
                if not externalReferenceMap[data.pdf].has_key(data.generation):
                    externalReferenceMap[data.pdf][data.generation] = {}
                externalReferenceMap[data.pdf][data.generation][data.idnum] = IndirectObject(objIndex + 1, 0, self)

        self.stack = []
        self._sweepIndirectReferences(externalReferenceMap, self._root)
        del self.stack

        # Begin writing:
        object_positions = []
        stream.write(self._header + "\n")
        for i in range(len(self._objects)):
            idnum = (i + 1)
            obj = self._objects[i]
            object_positions.append(stream.tell())
            stream.write(str(idnum) + " 0 obj\n")
            obj.writeToStream(stream, None)
            stream.write("\nendobj\n")

        # xref table
        xref_location = stream.tell()
        stream.write("xref\n")
        stream.write("0 %s\n" % (len(self._objects) + 1))
        stream.write("%010d %05d f \n" % (0, 65535))
        for offset in object_positions:
            stream.write("%010d %05d n \n" % (offset, 0))

        # trailer
        stream.write("trailer\n")
        trailer = DictionaryObject()
        trailer.update({
                NameObject("/Size"): NumberObject(len(self._objects) + 1),
                NameObject("/Root"): self._root,
                NameObject("/Info"): self._info,
                })
        if hasattr(self, "_ID"):
            trailer[NameObject("/ID")] = self._ID
        trailer.writeToStream(stream, None)
        
        # eof
        stream.write("\nstartxref\n%s\n%%%%EOF\n" % (xref_location))

    def _sweepIndirectReferences(self, externMap, data):
        if isinstance(data, DictionaryObject):
            for key, value in data.items():
                origvalue = value
                value = self._sweepIndirectReferences(externMap, value)
                if isinstance(value, StreamObject):
                    # a dictionary value is a stream.  streams must be indirect
                    # objects, so we need to change this value.
                    value = self._addObject(value)
                data[key] = value
            return data
        elif isinstance(data, ArrayObject):
            for i in range(len(data)):
                value = self._sweepIndirectReferences(externMap, data[i])
                if isinstance(value, StreamObject):
                    # an array value is a stream.  streams must be indirect
                    # objects, so we need to change this value
                    value = self._addObject(value)
                data[i] = value
            return data
        elif isinstance(data, IndirectObject):
            # internal indirect references are fine
            if data.pdf == self:
                if data.idnum in self.stack:
                    return data
                else:
                    self.stack.append(data.idnum)
                    realdata = self.getObject(data)
                    self._sweepIndirectReferences(externMap, realdata)
                    self.stack.pop()
                    return data
            else:
                newobj = externMap.get(data.pdf, {}).get(data.generation, {}).get(data.idnum, None)
                if newobj == None:
                    newobj = data.pdf.getObject(data)
                    self._objects.append(None) # placeholder
                    idnum = len(self._objects)
                    newobj_ido = IndirectObject(idnum, 0, self)
                    if not externMap.has_key(data.pdf):
                        externMap[data.pdf] = {}
                    if not externMap[data.pdf].has_key(data.generation):
                        externMap[data.pdf][data.generation] = {}
                    externMap[data.pdf][data.generation][data.idnum] = newobj_ido
                    newobj = self._sweepIndirectReferences(externMap, newobj)
                    self._objects[idnum-1] = newobj
                    return newobj_ido
                return newobj
        else:
            return data


##
# Initializes a PdfFileReader object.  This operation can take some time, as
# the PDF stream's cross-reference tables are read into memory.
# <p>
# Stability: Added in v1.0, will exist for all v1.x releases.
#
# @param stream An object that supports the standard read and seek methods
#               similar to a file object.
class PdfFileReader(object):
    def __init__(self, stream):
        self.flattenedPages = None
        self.resolvedObjects = {}
        self.read(stream)
        self.stream = stream
        self._override_encryption = False

    ##
    # Calculates the number of pages in this PDF file.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    # @return Returns an integer.
    def getNumPages(self):
        if self.flattenedPages == None:
            self._flatten()
        return len(self.flattenedPages)

    ##
    # Read-only property that accesses the {@link #PdfFileReader.getNumPages
    # getNumPages} function.
    # <p>
    # Stability: Added in v1.7, will exist for all future v1.x releases.
    numPages = property(lambda self: self.getNumPages(), None, None)

    ##
    # Retrieves a page by number from this PDF file.
    # <p>
    # Stability: Added in v1.0, will exist for all v1.x releases.
    # @return Returns a {@link #PageObject PageObject} instance.
    def getPage(self, pageNumber):
        ## ensure that we're not trying to access an encrypted PDF
        #assert not self.trailer.has_key("/Encrypt")
        if self.flattenedPages == None:
            self._flatten()
        return self.flattenedPages[pageNumber]

    ##
    # Read-only property that emulates a list based upon the {@link
    # #PdfFileReader.getNumPages getNumPages} and {@link #PdfFileReader.getPage
    # getPage} functions.
    # <p>
    # Stability: Added in v1.7, and will exist for all future v1.x releases.
    pages = property(lambda self: ConvertFunctionsToVirtualList(self.getNumPages, self.getPage),
            None, None)

    def _flatten(self, pages=None, inherit=None, indirectRef=None):
        inheritablePageAttributes = (
            NameObject("/Resources"), NameObject("/MediaBox"),
            NameObject("/CropBox"), NameObject("/Rotate")
            )
        if inherit == None:
            inherit = dict()
        if pages == None:
            self.flattenedPages = []
            catalog = self.trailer["/Root"].getObject()
            pages = catalog["/Pages"].getObject()
        t = pages["/Type"]
        if t == "/Pages":
            for attr in inheritablePageAttributes:
                if pages.has_key(attr):
                    inherit[attr] = pages[attr]
            for page in pages["/Kids"]:
                addt = {}
                if isinstance(page, IndirectObject):
                    addt["indirectRef"] = page
                self._flatten(page.getObject(), inherit, **addt)
        elif t == "/Page":
            for attr,value in inherit.items():
                # if the page has it's own value, it does not inherit the
                # parent's value:
                if not pages.has_key(attr):
                    pages[attr] = value
            pageObj = PageObject(self, indirectRef)
            pageObj.update(pages)
            self.flattenedPages.append(pageObj)

    def getObject(self, indirectReference):
        retval = self.resolvedObjects.get(indirectReference.generation, {}).get(indirectReference.idnum, None)
        if retval != None:
            return retval
        if indirectReference.generation == 0 and \
           self.xref_objStm.has_key(indirectReference.idnum):
            # indirect reference to object in object stream
            # read the entire object stream into memory
            stmnum,idx = self.xref_objStm[indirectReference.idnum]
            objStm = IndirectObject(stmnum, 0, self).getObject()
            assert objStm['/Type'] == '/ObjStm'
            assert idx < objStm['/N']
            streamData = StringIO(objStm.getData())
            for i in range(objStm['/N']):
                objnum = NumberObject.readFromStream(streamData)
                readNonWhitespace(streamData)
                streamData.seek(-1, 1)
                offset = NumberObject.readFromStream(streamData)
                readNonWhitespace(streamData)
                streamData.seek(-1, 1)
                t = streamData.tell()
                streamData.seek(objStm['/First']+offset, 0)
                obj = readObject(streamData, self)
                self.resolvedObjects[0][objnum] = obj
                streamData.seek(t, 0)
            return self.resolvedObjects[0][indirectReference.idnum]
        start = self.xref[indirectReference.generation][indirectReference.idnum]
        self.stream.seek(start, 0)
        idnum, generation = self.readObjectHeader(self.stream)
        assert idnum == indirectReference.idnum
        assert generation == indirectReference.generation
        retval = readObject(self.stream, self)

        # override encryption is used for the /Encrypt dictionary
        if not self._override_encryption and self.isEncrypted:
            # if we don't have the encryption key:
            if not hasattr(self, '_decryption_key'):
                raise Exception, "file has not been decrypted"
            # otherwise, decrypt here...
            import struct
            pack1 = struct.pack("<i", indirectReference.idnum)[:3]
            pack2 = struct.pack("<i", indirectReference.generation)[:2]
            key = self._decryption_key + pack1 + pack2
            assert len(key) == (len(self._decryption_key) + 5)
            md5_hash = md5(key).digest()
            key = md5_hash[:min(16, len(self._decryption_key) + 5)]
            retval = self._decryptObject(retval, key)

        self.cacheIndirectObject(generation, idnum, retval)
        return retval

    def _decryptObject(self, obj, key):
        if isinstance(obj, ByteStringObject) or isinstance(obj, TextStringObject):
            obj = createStringObject(utils.RC4_encrypt(key, obj.original_bytes))
        elif isinstance(obj, StreamObject):
            obj._data = utils.RC4_encrypt(key, obj._data)
        elif isinstance(obj, DictionaryObject):
            for dictkey, value in obj.items():
                obj[dictkey] = self._decryptObject(value, key)
        elif isinstance(obj, ArrayObject):
            for i in range(len(obj)):
                obj[i] = self._decryptObject(obj[i], key)
        return obj

    def readObjectHeader(self, stream):
        # Should never be necessary to read out whitespace, since the
        # cross-reference table should put us in the right spot to read the
        # object header.  In reality... some files have stupid cross reference
        # tables that are off by whitespace bytes.
        readNonWhitespace(stream); stream.seek(-1, 1)
        idnum = readUntilWhitespace(stream)
        generation = readUntilWhitespace(stream)
        obj = stream.read(3)
        readNonWhitespace(stream)
        stream.seek(-1, 1)
        return int(idnum), int(generation)

    def cacheIndirectObject(self, generation, idnum, obj):
        if not self.resolvedObjects.has_key(generation):
            self.resolvedObjects[generation] = {}
        self.resolvedObjects[generation][idnum] = obj

    def read(self, stream):
        # start at the end:
        stream.seek(-1, 2)
        line = ''
        while not line:
            line = self.readNextEndLine(stream)
        if line[:5] != "%%EOF":
            raise utils.PdfReadError, "EOF marker not found"

        # find startxref entry - the location of the xref table
        line = self.readNextEndLine(stream)
        startxref = int(line)
        line = self.readNextEndLine(stream)
        if line[:9] != "startxref":
            raise utils.PdfReadError, "startxref not found"

        # read all cross reference tables and their trailers
        self.xref = {}
        self.xref_objStm = {}
        self.trailer = DictionaryObject()
        while 1:
            # load the xref table
            stream.seek(startxref, 0)
            x = stream.read(1)
            if x == "x":
                # standard cross-reference table
                ref = stream.read(4)
                if ref[:3] != "ref":
                    raise utils.PdfReadError, "xref table read error"
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                while 1:
                    num = readObject(stream, self)
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    size = readObject(stream, self)
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    cnt = 0
                    while cnt < size:
                        line = stream.read(20)
                        # It's very clear in section 3.4.3 of the PDF spec
                        # that all cross-reference table lines are a fixed
                        # 20 bytes.  However... some malformed PDF files
                        # use a single character EOL without a preceeding
                        # space.  Detect that case, and seek the stream
                        # back one character.  (0-9 means we've bled into
                        # the next xref entry, t means we've bled into the
                        # text "trailer"):
                        if line[-1] in "0123456789t":
                            stream.seek(-1, 1)
                        offset, generation = line[:16].split(" ")
                        offset, generation = int(offset), int(generation)
                        if not self.xref.has_key(generation):
                            self.xref[generation] = {}
                        if self.xref[generation].has_key(num):
                            # It really seems like we should allow the last
                            # xref table in the file to override previous
                            # ones. Since we read the file backwards, assume
                            # any existing key is already set correctly.
                            pass
                        else:
                            self.xref[generation][num] = offset
                        cnt += 1
                        num += 1
                    readNonWhitespace(stream)
                    stream.seek(-1, 1)
                    trailertag = stream.read(7)
                    if trailertag != "trailer":
                        # more xrefs!
                        stream.seek(-7, 1)
                    else:
                        break
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                newTrailer = readObject(stream, self)
                for key, value in newTrailer.items():
                    if not self.trailer.has_key(key):
                        self.trailer[key] = value
                if newTrailer.has_key("/Prev"):
                    startxref = newTrailer["/Prev"]
                else:
                    break
            elif x.isdigit():
                # PDF 1.5+ Cross-Reference Stream
                stream.seek(-1, 1)
                idnum, generation = self.readObjectHeader(stream)
                xrefstream = readObject(stream, self)
                assert xrefstream["/Type"] == "/XRef"
                self.cacheIndirectObject(generation, idnum, xrefstream)
                streamData = StringIO(xrefstream.getData())
                idx_pairs = xrefstream.get("/Index", [0, xrefstream.get("/Size")])
                entrySizes = xrefstream.get("/W")
                for num, size in self._pairs(idx_pairs):
                    cnt = 0
                    while cnt < size:
                        for i in range(len(entrySizes)):
                            d = streamData.read(entrySizes[i])
                            di = convertToInt(d, entrySizes[i])
                            if i == 0:
                                xref_type = di
                            elif i == 1:
                                if xref_type == 0:
                                    next_free_object = di
                                elif xref_type == 1:
                                    byte_offset = di
                                elif xref_type == 2:
                                    objstr_num = di
                            elif i == 2:
                                if xref_type == 0:
                                    next_generation = di
                                elif xref_type == 1:
                                    generation = di
                                elif xref_type == 2:
                                    obstr_idx = di
                        if xref_type == 0:
                            pass
                        elif xref_type == 1:
                            if not self.xref.has_key(generation):
                                self.xref[generation] = {}
                            if not num in self.xref[generation]:
                                self.xref[generation][num] = byte_offset
                        elif xref_type == 2:
                            if not num in self.xref_objStm:
                                self.xref_objStm[num] = [objstr_num, obstr_idx]
                        cnt += 1
                        num += 1
                trailerKeys = "/Root", "/Encrypt", "/Info", "/ID"
                for key in trailerKeys:
                    if xrefstream.has_key(key) and not self.trailer.has_key(key):
                        self.trailer[NameObject(key)] = xrefstream.raw_get(key)
                if xrefstream.has_key("/Prev"):
                    startxref = xrefstream["/Prev"]
                else:
                    break
            else:
                # bad xref character at startxref.  Let's see if we can find
                # the xref table nearby, as we've observed this error with an
                # off-by-one before.
                stream.seek(-11, 1)
                tmp = stream.read(20)
                xref_loc = tmp.find("xref")
                if xref_loc != -1:
                    startxref -= (10 - xref_loc)
                    continue
                else:
                    # no xref table found at specified location
                    assert False
                    break

    def _pairs(self, array):
        i = 0
        while True:
            yield array[i], array[i+1]
            i += 2
            if (i+1) >= len(array):
                break

    def readNextEndLine(self, stream):
        line = ""
        while True:
            x = stream.read(1)
            stream.seek(-2, 1)
            if x == '\n' or x == '\r':
                while x == '\n' or x == '\r':
                    x = stream.read(1)
                    stream.seek(-2, 1)
                stream.seek(1, 1)
                break
            else:
                line = x + line
        return line

    ##
    # When using an encrypted / secured PDF file with the PDF Standard
    # encryption handler, this function will allow the file to be decrypted.
    # It checks the given password against the document's user password and
    # owner password, and then stores the resulting decryption key if either
    # password is correct.
    # <p>
    # It does not matter which password was matched.  Both passwords provide
    # the correct decryption key that will allow the document to be used with
    # this library.
    # <p>
    # Stability: Added in v1.8, will exist for all future v1.x releases.
    #
    # @return 0 if the password failed, 1 if the password matched the user
    # password, and 2 if the password matched the owner password.
    #
    # @exception NotImplementedError Document uses an unsupported encryption
    # method.
    def decrypt(self, password):
        self._override_encryption = True
        try:
            return self._decrypt(password)
        finally:
            self._override_encryption = False

    def _decrypt(self, password):
        encrypt = self.trailer['/Encrypt'].getObject()
        if encrypt['/Filter'] != '/Standard':
            raise NotImplementedError, "only Standard PDF encryption handler is available"
        if not (encrypt['/V'] in (1, 2)):
            raise NotImplementedError, "only algorithm code 1 and 2 are supported"
        user_password, key = self._authenticateUserPassword(password)
        if user_password:
            self._decryption_key = key
            return 1
        else:
            rev = encrypt['/R'].getObject()
            if rev == 2:
                keylen = 5
            else:
                keylen = encrypt['/Length'].getObject() / 8
            key = _alg33_1(password, rev, keylen)
            real_O = encrypt["/O"].getObject()
            if rev == 2:
                userpass = utils.RC4_encrypt(key, real_O)
            else:
                val = real_O
                for i in range(19, -1, -1):
                    new_key = ''
                    for l in range(len(key)):
                        new_key += chr(ord(key[l]) ^ i)
                    val = utils.RC4_encrypt(new_key, val)
                userpass = val
            owner_password, key = self._authenticateUserPassword(userpass)
            if owner_password:
                self._decryption_key = key
                return 2
        return 0

    def _authenticateUserPassword(self, password):
        encrypt = self.trailer['/Encrypt'].getObject()
        rev = encrypt['/R'].getObject()
        owner_entry = encrypt['/O'].getObject().original_bytes
        p_entry = encrypt['/P'].getObject()
        id_entry = self.trailer['/ID'].getObject()
        id1_entry = id_entry[0].getObject()
        if rev == 2:
            U, key = _alg34(password, owner_entry, p_entry, id1_entry)
        elif rev >= 3:
            U, key = _alg35(password, rev,
                    encrypt["/Length"].getObject() / 8, owner_entry,
                    p_entry, id1_entry,
                    encrypt.get("/EncryptMetadata", BooleanObject(False)).getObject())
        real_U = encrypt['/U'].getObject().original_bytes
        return U == real_U, key

    def getIsEncrypted(self):
        return self.trailer.has_key("/Encrypt")

    ##
    # Read-only boolean property showing whether this PDF file is encrypted.
    # Note that this property, if true, will remain true even after the {@link
    # #PdfFileReader.decrypt decrypt} function is called.
    isEncrypted = property(lambda self: self.getIsEncrypted(), None, None)


##
# This class represents a single page within a PDF file.  Typically this object
# will be created by accessing the {@link #PdfFileReader.getPage getPage}
# function of the {@link #PdfFileReader PdfFileReader} class, but it is
# also possible to create an empty page with the createBlankPage static
# method.
# @param pdf PDF file the page belongs to (optional, defaults to None).
class PageObject(DictionaryObject):
    def __init__(self, pdf=None, indirectRef=None):
        DictionaryObject.__init__(self)
        self.pdf = pdf
        # Stores the original indirect reference to this object in its source PDF
        self.indirectRef = indirectRef

def convertToInt(d, size):
    if size > 8:
        raise utils.PdfReadError("invalid size in convertToInt")
    d = "\x00\x00\x00\x00\x00\x00\x00\x00" + d
    d = d[-8:]
    return struct.unpack(">q", d)[0]

# ref: pdf1.8 spec section 3.5.2 algorithm 3.2
_encryption_padding = '\x28\xbf\x4e\x5e\x4e\x75\x8a\x41\x64\x00\x4e\x56' + \
        '\xff\xfa\x01\x08\x2e\x2e\x00\xb6\xd0\x68\x3e\x80\x2f\x0c' + \
        '\xa9\xfe\x64\x53\x69\x7a'

# Implementation of algorithm 3.2 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry, metadata_encrypt=True):
    # 1. Pad or truncate the password string to exactly 32 bytes.  If the
    # password string is more than 32 bytes long, use only its first 32 bytes;
    # if it is less than 32 bytes long, pad it by appending the required number
    # of additional bytes from the beginning of the padding string
    # (_encryption_padding).
    password = (password + _encryption_padding)[:32]
    # 2. Initialize the MD5 hash function and pass the result of step 1 as
    # input to this function.
    import struct
    m = md5(password)
    # 3. Pass the value of the encryption dictionary's /O entry to the MD5 hash
    # function.
    m.update(owner_entry)
    # 4. Treat the value of the /P entry as an unsigned 4-byte integer and pass
    # these bytes to the MD5 hash function, low-order byte first.
    p_entry = struct.pack('<i', p_entry)
    m.update(p_entry)
    # 5. Pass the first element of the file's file identifier array to the MD5
    # hash function.
    m.update(id1_entry)
    # 6. (Revision 3 or greater) If document metadata is not being encrypted,
    # pass 4 bytes with the value 0xFFFFFFFF to the MD5 hash function.
    if rev >= 3 and not metadata_encrypt:
        m.update("\xff\xff\xff\xff")
    # 7. Finish the hash.
    md5_hash = m.digest()
    # 8. (Revision 3 or greater) Do the following 50 times: Take the output
    # from the previous MD5 hash and pass the first n bytes of the output as
    # input into a new MD5 hash, where n is the number of bytes of the
    # encryption key as defined by the value of the encryption dictionary's
    # /Length entry.
    if rev >= 3:
        for i in range(50):
            md5_hash = md5(md5_hash[:keylen]).digest()
    # 9. Set the encryption key to the first n bytes of the output from the
    # final MD5 hash, where n is always 5 for revision 2 but, for revision 3 or
    # greater, depends on the value of the encryption dictionary's /Length
    # entry.
    return md5_hash[:keylen]

# Steps 1-4 of algorithm 3.3
def _alg33_1(password, rev, keylen):
    # 1. Pad or truncate the owner password string as described in step 1 of
    # algorithm 3.2.  If there is no owner password, use the user password
    # instead.
    password = (password + _encryption_padding)[:32]
    # 2. Initialize the MD5 hash function and pass the result of step 1 as
    # input to this function.
    m = md5(password)
    # 3. (Revision 3 or greater) Do the following 50 times: Take the output
    # from the previous MD5 hash and pass it as input into a new MD5 hash.
    md5_hash = m.digest()
    if rev >= 3:
        for i in range(50):
            md5_hash = md5(md5_hash).digest()
    # 4. Create an RC4 encryption key using the first n bytes of the output
    # from the final MD5 hash, where n is always 5 for revision 2 but, for
    # revision 3 or greater, depends on the value of the encryption
    # dictionary's /Length entry.
    key = md5_hash[:keylen]
    return key

# Implementation of algorithm 3.4 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg34(password, owner_entry, p_entry, id1_entry):
    # 1. Create an encryption key based on the user password string, as
    # described in algorithm 3.2.
    key = _alg32(password, 2, 5, owner_entry, p_entry, id1_entry)
    # 2. Encrypt the 32-byte padding string shown in step 1 of algorithm 3.2,
    # using an RC4 encryption function with the encryption key from the
    # preceding step.
    U = utils.RC4_encrypt(key, _encryption_padding)
    # 3. Store the result of step 2 as the value of the /U entry in the
    # encryption dictionary.
    return U, key

# Implementation of algorithm 3.4 of the PDF standard security handler,
# section 3.5.2 of the PDF 1.6 reference.
def _alg35(password, rev, keylen, owner_entry, p_entry, id1_entry, metadata_encrypt):
    # 1. Create an encryption key based on the user password string, as
    # described in Algorithm 3.2.
    key = _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry)
    # 2. Initialize the MD5 hash function and pass the 32-byte padding string
    # shown in step 1 of Algorithm 3.2 as input to this function. 
    m = md5()
    m.update(_encryption_padding)
    # 3. Pass the first element of the file's file identifier array (the value
    # of the ID entry in the document's trailer dictionary; see Table 3.13 on
    # page 73) to the hash function and finish the hash.  (See implementation
    # note 25 in Appendix H.) 
    m.update(id1_entry)
    md5_hash = m.digest()
    # 4. Encrypt the 16-byte result of the hash, using an RC4 encryption
    # function with the encryption key from step 1. 
    val = utils.RC4_encrypt(key, md5_hash)
    # 5. Do the following 19 times: Take the output from the previous
    # invocation of the RC4 function and pass it as input to a new invocation
    # of the function; use an encryption key generated by taking each byte of
    # the original encryption key (obtained in step 2) and performing an XOR
    # operation between that byte and the single-byte value of the iteration
    # counter (from 1 to 19). 
    for i in range(1, 20):
        new_key = ''
        for l in range(len(key)):
            new_key += chr(ord(key[l]) ^ i)
        val = utils.RC4_encrypt(new_key, val)
    # 6. Append 16 bytes of arbitrary padding to the output from the final
    # invocation of the RC4 function and store the 32-byte result as the value
    # of the U entry in the encryption dictionary. 
    # (implementator note: I don't know what "arbitrary padding" is supposed to
    # mean, so I have used null bytes.  This seems to match a few other
    # people's implementations)
    return val + ('\x00' * 16), key

#if __name__ == "__main__":
#    output = PdfFileWriter()
#
#    input1 = PdfFileReader(file("test\\5000-s1-05e.pdf", "rb"))
#    page1 = input1.getPage(0)
#
#    input2 = PdfFileReader(file("test\\PDFReference16.pdf", "rb"))
#    page2 = input2.getPage(0)
#    page3 = input2.getPage(1)
#    page1.mergePage(page2)
#    page1.mergePage(page3)
#
#    input3 = PdfFileReader(file("test\\cc-cc.pdf", "rb"))
#    page1.mergePage(input3.getPage(0))
#
#    page1.compressContentStreams()
#
#    output.addPage(page1)
#    output.write(file("test\\merge-test.pdf", "wb"))


