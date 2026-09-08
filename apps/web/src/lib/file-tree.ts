export type TreeNode = { name: string; path: string; fileId?: string; children: TreeNode[] };

export function buildFileTree(files: { path: string; id: string }[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", children: [] };
  const directories = new Map<string, TreeNode>([["", root]]);
  for (const file of files) {
    const parts = file.path.split("/");
    let parent = root;
    for (let index = 0; index < parts.length; index++) {
      const path = parts.slice(0, index + 1).join("/");
      if (index === parts.length - 1) {
        parent.children.push({ name: parts[index], path, fileId: file.id, children: [] });
      } else {
        let directory = directories.get(path);
        if (!directory) {
          directory = { name: parts[index], path, children: [] };
          directories.set(path, directory);
          parent.children.push(directory);
        }
        parent = directory;
      }
    }
  }
  for (const directory of directories.values()) {
    directory.children.sort((a, b) => Number(Boolean(a.fileId)) - Number(Boolean(b.fileId)) || a.name.localeCompare(b.name));
  }
  return root.children;
}
