import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Tuple, BinaryIO
from dataclasses import dataclass

@dataclass
class RefValue:
    """Represents a Git reference value"""
    symbolic: bool
    value: str

class GitDataManager:
    """Manages Git data storage and operations"""
    def __init__(self):
        self.GIT_DIR = '.gitter'
        self.OBJECTS_DIR = f'{self.GIT_DIR}/objects'
        self.INDEX_PATH = f'{self.GIT_DIR}/index'
        self._index: Optional[Dict[str, str]] = None

    def init(self):
        """Initialize Git directory structure"""
        os.makedirs(self.GIT_DIR)
        os.makedirs(self.OBJECTS_DIR)

    def hash_object(self, data: bytes, type_: str = 'blob'):
        """Hash and store an object"""
        obj = type_.encode() + b'\x00' + data
        oid = hashlib.sha1(obj).hexdigest()
        with open(f'{self.OBJECTS_DIR}/{oid}', 'wb') as out:
            out.write(obj)
        return oid

    def get_object(self, oid: str, expected: Optional[str] = None):
        """Retrieve an object by its hash"""
        with open(f'{self.OBJECTS_DIR}/{oid}', 'rb') as f:
            obj = f.read()

        type_, _, content = obj.partition(b'\x00')
        type_ = type_.decode()

        if expected is not None:
            assert type_ == expected, f'Expected {expected}, got {type_}'
        return content

    @contextmanager
    def get_index(self):
        """Get the current index"""
        if self._index is None:
            self._index = {}
            if os.path.isfile(self.INDEX_PATH):
                with open(self.INDEX_PATH) as f:
                    self._index = json.load(f)

        yield self._index

        with open(self.INDEX_PATH, 'w') as f:
            json.dump(self._index, f)

    def update_ref(self, ref: str, value: RefValue, deref: bool = True):
        """Update a reference to point to a specific value"""
        ref = self._get_ref_internal(ref, deref)[0]

        assert value.value
        if value.symbolic:
            value = f'ref: {value.value}'
        else:
            value = value.value

        ref_path = f'{self.GIT_DIR}/{ref}'
        os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        with open(ref_path, 'w') as f:
            f.write(value)

    def get_ref(self, ref: str, deref: bool = True):
        """Get the value of a reference"""
        return self._get_ref_internal(ref, deref)[1]

    def _get_ref_internal(self, ref: str, deref: bool):
        """Internal method to get reference value"""
        ref_path = f'{self.GIT_DIR}/{ref}'
        value = None
        if os.path.isfile(ref_path):
            with open(ref_path) as f:
                value = f.read().strip()

        symbolic = bool(value and value.startswith('ref:'))
        if symbolic:
            value = value.split(':', 1)[1].strip()
            if deref:
                return self._get_ref_internal(value, True)

        return ref, RefValue(symbolic=symbolic, value=value)

    def delete_ref(self, ref: str, deref: bool = True):
        """Delete a reference"""
        ref = self._get_ref_internal(ref, deref)[0]
        os.remove(f'{self.GIT_DIR}/{ref}')

    def iter_refs(self, prefix: str = '', deref: bool = True):
        """Iterate through all references"""
        refs = ['HEAD']
        for root, _, filenames in os.walk(f'{self.GIT_DIR}/refs/'):
            root = os.path.relpath(root, self.GIT_DIR)
            refs.extend(f'{root}/{name}' for name in filenames)

        for ref in refs:
            if not ref.startswith(prefix):
                continue
            ref = ref.replace('\\', '/')
            yield ref, self.get_ref(ref, deref=deref)


class GitContext:
    """Context manager for Git directory operations"""
    def __init__(self, git_dir: str):
        self.git_dir = git_dir
        self.original = None

    def __enter__(self):
        self.original = os.getcwd()
        os.chdir(self.git_dir)

    def __exit__(self, type_, value, traceback):
        os.chdir(self.original)


@contextmanager
def change_git_dir(new_dir: str):
    """Change Git directory temporarily"""
    with GitContext(new_dir):
        yield
