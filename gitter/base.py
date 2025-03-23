import itertools
import operator
import os
import string
from collections import defaultdict, deque, namedtuple
from typing import List, Set, Dict, Optional, Iterator, Any
from dataclasses import dataclass
import subprocess

from collections import defaultdict
from tempfile import NamedTemporaryFile as Temp


from gitter import data
from gitter.data import GitDataManager


@dataclass
class Commit:
    """Represents a Git commit object"""
    tree: str
    parents: List[str]
    message: str

class TreeUtils:
    """Utility class for tree-related operations"""
    def __init__(self, data_manager):
        self.data_manager = data_manager

    def write_tree_recursive(self, tree_dict: Dict):
        entries = []
        for name, value in tree_dict.items():
            if isinstance(value, dict):
                type_ = 'tree'
                oid = self.write_tree_recursive(value)
            else:
                type_ = 'blob'
                oid = value
            entries.append((name, oid, type_))

        tree = ''.join(f'{type_} {oid} {name}\n'
                        for name, oid, type_
                      in sorted(entries))
        return self.data_manager.hash_object(tree.encode(), 'tree')

    def iter_tree_entries(self, oid: str):
        if not oid:
            return
        tree = self.data_manager.get_object(oid, 'tree')
        for entry in tree.decode().splitlines():
            type_, oid, name = entry.split(' ', 2)
            yield type_, oid, name

    def build_tree_dict(self):
        index_as_tree = {}
        with self.data_manager.get_index() as index:
            for path, oid in index.items():
                path = path.split('/')
                dirpath, filename = path[:-1], path[-1]

                current = index_as_tree
                for dirname in dirpath:
                    current = current.setdefault(dirname, {})
                current[filename] = oid
        return index_as_tree

    def get_tree(self, oid: str, base_path: str = ''):
        result = {}
        for type_, oid, name in self.iter_tree_entries(oid):
            assert '/' not in name
            assert name not in ('..', '.')
            path = base_path + name
            if type_ == 'blob':
                result[path] = oid
            elif type_ == 'tree':
                result.update(self.get_tree(oid, f'{path}/'))
            else:
                assert False, f'Unknown tree entry {type_}'
        return result

class WorkingDirectoryUtils:
    """Utility class for working directory operations"""
    def __init__(self, data_manager, ignore_handler):
        self.data_manager = data_manager
        self.ignore_handler = ignore_handler


    def get_working_tree(self):
        result = {}
        for root, _, filenames in os.walk('.'):
            for filename in filenames:
                path = os.path.relpath(f'{root}/{filename}')
                if self.ignore_handler.is_ignored(path) or not os.path.isfile(path):
                    continue
                with open(path, 'rb') as f:
                        result[path] = self.data_manager.hash_object(f.read())
        return result
    
    def get_index_tree(self):
        """Get current index state"""
        with self.data_manager.get_index() as index:
            return index

class ReferenceUtils:
    """Utility class for handling Git references"""
    def __init__(self, data_manager):
        self.data_manager = data_manager

    def get_oid(self, name: str):
        if name == '@':
            name = 'HEAD'

        refs_to_try = [
            f'{name}',
            f'refs/{name}',
            f'refs/tags/{name}',
            f'refs/heads/{name}',
        ]
        
        for ref in refs_to_try:
            if self.data_manager.get_ref(ref, deref=False).value:
                return self.data_manager.get_ref(ref).value

        is_hex = all(c in string.hexdigits for c in name)
        if len(name) == 40 and is_hex:
            return name

        assert False, f'Unknown name {name}'


    def get_branch_name(self):
        HEAD = self.data_manager.get_ref('HEAD', deref=False)
        if not HEAD.symbolic:
            return None
        HEAD = HEAD.value
        assert HEAD.startswith('refs/heads/')
        return os.path.relpath(HEAD, 'refs/heads')



class CommitUtils:
    """Utility class for commit operations"""
    def __init__(self, data_manager):
        self.data_manager = data_manager
        self.ignore_handler = GitIgnore()

    def get_commit(self, oid: str):
        parents = []
        commit = self.data_manager.get_object(oid, 'commit').decode()
        lines = iter(commit.splitlines())
        
        for line in itertools.takewhile(operator.truth, lines):
            key, value = line.split(' ', 1)
            if key == 'tree':
                tree = value
            elif key == 'parent':
                parents.append(value)
            else:
                assert False, f'Unknown field {key}'

        message = '\n'.join(lines)
        return Commit(tree=tree, parents=parents, message=message)

    def iter_commits_and_parents(self, oids: Set[str]):
        oids = deque(oids)
        visited = set()

        while oids:
            oid = oids.popleft()
            if not oid or oid in visited:
                continue
            visited.add(oid)
            yield oid

            commit = self.get_commit(oid)
            oids.extendleft(commit.parents[:1])
            oids.extend(commit.parents[1:])

    
    def _add_file(self, filename: str):
        """Helper method to add a single file"""
        filename = os.path.relpath(filename)
        if self.ignore_handler.is_ignored(filename):
            print(f'Ignoring {filename} (matched .gitignore pattern)')
            return
        with open(filename, 'rb') as f:
            oid = self.data_manager.hash_object(f.read())
        with self.data_manager.get_index() as index:
            index[filename] = oid

    def _add_directory(self, dirname: str):
        """Helper method to add a directory"""
        for root, _, filenames in os.walk(dirname):
            for filename in filenames:
                path = os.path.relpath(f'{root}/{filename}')
                if self.ignore_handler.is_ignored(path):
                    print(f'Ignoring {path} (matched .gitignore pattern)')
                    continue
                if not os.path.isfile(path):
                    continue
                self._add_file(path)

class diffUtils:
    """Utility class for diff operations"""
    def __init__(self, data_manager):
        self.data_manager = data_manager

    def compare_trees (self, *trees):
        entries = defaultdict (lambda: [None] * len (trees))
        for i, tree in enumerate (trees):
            for path, oid in tree.items ():
                entries[path][i] = oid

        for path, oids in entries.items ():
            yield (path, *oids)


    def iter_changed_files (self, t_from, t_to):
        for path, o_from, o_to in self.compare_trees (t_from, t_to):
            if o_from != o_to:
                action = ('new file' if not o_from else
                        'deleted' if not o_to else
                        'modified')
                yield path, action


    def diff_trees (self, t_from, t_to):
        output = b''
        for path, o_from, o_to in self.compare_trees (t_from, t_to):
            if o_from != o_to:
                output += self.diff_blobs (o_from, o_to, path)
        return output


    def diff_blobs (self, o_from, o_to, path='blob'):
        with Temp () as f_from, Temp () as f_to:
            for oid, f in ((o_from, f_from), (o_to, f_to)):
                if oid:
                    f.write (self.data_manager.get_object (oid))
                    f.flush ()

            with subprocess.Popen (
                ['diff', '--unified', '--show-c-function',
                '--label', f'a/{path}', f_from.name,
                '--label', f'b/{path}', f_to.name],
                stdout=subprocess.PIPE) as proc:
                output, _ = proc.communicate ()

            return output

class GitIgnore:
    """Handles .gitignore patterns and matching"""
    def __init__(self):
        self.patterns = self._get_ignore_patterns()

    def _get_ignore_patterns(self):
        patterns = []
        try:
            with open('.gitterignore', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.append(line)
        except FileNotFoundError:
            pass
        return patterns

    def is_ignored(self, path: str):
        parts = path.split('\\')
        return any(pattern in parts for pattern in self.patterns)

class GitCommand:
    """Main class handling all Git commands"""
    def __init__(self):
        self.data_manager = GitDataManager()
        self.ignore_handler = GitIgnore()
        
        # Initialize utility classes
        self.tree_utils = TreeUtils(self.data_manager)
        self.working_dir_utils = WorkingDirectoryUtils(self.data_manager, self.ignore_handler)
        self.ref_utils = ReferenceUtils(self.data_manager)
        self.commit_utils = CommitUtils(self.data_manager)
        self.diff_utils = diffUtils(self.data_manager)

    def init(self):
        """Initialize a new Git repository"""
        self.data_manager.init()
        self.data_manager.update_ref('HEAD',
            data.RefValue(symbolic=True, value='refs/heads/main'))

    def add(self, filenames: List[str]):
        """Add files to the index"""
        for name in filenames:
            if os.path.isfile(name):
                self.commit_utils._add_file(name)
            elif os.path.isdir(name):
                self.commit_utils._add_directory(name)

    def commit(self, message: str):
        """Create a new commit"""
        commit = f'tree {self.tree_utils.write_tree_recursive(self.tree_utils.build_tree_dict())}\n'

        HEAD = self.data_manager.get_ref('HEAD').value
        if HEAD:
            commit += f'parent {HEAD}\n'
        MERGE_HEAD = self.data_manager.get_ref('MERGE_HEAD').value
        if MERGE_HEAD:
            commit += f'parent {MERGE_HEAD}\n'
            self.data_manager.delete_ref('MERGE_HEAD', deref=False)

        commit += f'\n{message}\n'
        oid = self.data_manager.hash_object(commit.encode(), 'commit')
        self.data_manager.update_ref('HEAD',
                                   data.RefValue(symbolic=False, value=oid))
        return oid

    def status(self):
        """Show repository status"""
        HEAD = self.ref_utils.get_oid('@')
        branch = self.ref_utils.get_branch_name()
        if branch:
            print(f'On branch {branch}')
        else:
            print(f'HEAD detached at {HEAD[:10]}')

        MERGE_HEAD = self.data_manager.get_ref('MERGE_HEAD').value
        if MERGE_HEAD:
            print(f'Merging with {MERGE_HEAD[:10]}')

        print('\nChanges to be committed:\n')
        HEAD_tree = HEAD and self.commit_utils.get_commit(HEAD).tree
        for path, action in self.diff_utils.iter_changed_files(
            self.tree_utils.get_tree(HEAD_tree),
            self.working_dir_utils.get_index_tree()
        ):
            print(f'{action:>12}: {path}')

        print('\nChanges not staged for commit:\n')
        for path, action in self.diff_utils.iter_changed_files(
            self.working_dir_utils.get_index_tree(),
            self.working_dir_utils.get_working_tree()
        ):
            print(f'{action:>12}: {path}')

    def log(self, oid: str):
        """
        Get commit log history with references
        Returns a list of tuples containing (oid, commit, refs)
        """
        # Build reference mapping
        refs = {}
        for refname, ref in self.data_manager.iter_refs():
            refs.setdefault(ref.value, []).append(refname)

        # Build log entries
        log_entries = []
        for commit_oid in self.commit_utils.iter_commits_and_parents({oid}):
            commit = self.commit_utils.get_commit(commit_oid)
            log_entries.append((
                commit_oid,
                commit,
                refs.get(commit_oid)
            ))
        
        return log_entries

    def diff(self, commit: Optional[str] = None, cached: bool = False):
        """
        Generate diff between different states of the repository
        Args:
            commit: Optional commit to diff against
            cached: Whether to show staged changes
        Returns:
            Diff output as bytes
        """
        oid = commit and self.ref_utils.get_oid(commit)
        tree_from = None
        tree_to = None

        # Determine source tree (tree_from)
        if commit:
            # If commit provided, diff from that commit's tree
            tree_from = self.tree_utils.get_tree(
                oid and self.commit_utils.get_commit(oid).tree
            )
        
        # Determine target tree (tree_to) and default source tree
        if cached:
            # Show staged changes
            tree_to = self.working_dir_utils.get_index_tree()
            if not commit:
                # If no commit specified, diff from HEAD
                oid = self.ref_utils.get_oid('@')
                tree_from = self.tree_utils.get_tree(
                    oid and self.commit_utils.get_commit(oid).tree
                )
        else:
            # Show working directory changes
            tree_to = self.working_dir_utils.get_working_tree()
            if not commit:
                # If no commit specified, diff from index
                tree_from = self.working_dir_utils.get_index_tree()

        # Generate and return diff
        return self.diff_utils.diff_trees(tree_from, tree_to)
