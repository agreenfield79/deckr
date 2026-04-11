export interface TreeNode {
  name: string
  path: string
  type: 'file' | 'folder'
  children?: TreeNode[]
}

export interface TreeResponse {
  items: TreeNode[]
}

export interface ActiveFile {
  path: string
  content: string
}
