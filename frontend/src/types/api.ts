export interface RoleBrief {
  code: string;
  name: string;
}

export interface DepartmentBrief {
  id: string;
  name: string;
}

export interface UserBrief {
  id: string;
  name: string;
}

export interface CurrentUser {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  roles: RoleBrief[];
  department: DepartmentBrief | null;
  manager: UserBrief | null;
  permissions: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

export interface UserResponse {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  roles: RoleBrief[];
  department: DepartmentBrief | null;
  manager: UserBrief | null;
}

export interface UserListResponse {
  items: UserResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface PermissionBrief {
  code: string;
  name: string;
}

export interface RoleResponse {
  code: string;
  name: string;
  description: string | null;
  permissions: PermissionBrief[];
}

export interface DepartmentNode {
  id: string;
  name: string;
  parent_id: string | null;
  member_count: number;
  children: DepartmentNode[];
}

export interface DepartmentResponse {
  id: string;
  name: string;
  parent_id: string | null;
}

export interface UserOrgUpdate {
  department_id?: string | null;
  manager_id?: string | null;
}

export type LeaveType = "personal" | "sick" | "annual" | "compensatory";
export type LeaveStatus = "pending" | "approved" | "rejected" | "canceled";

export interface LeaveResponse {
  id: string;
  type: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: string;
  applicant: UserBrief;
  approver: UserBrief;
  created_at: string;
}

export interface LeaveHistoryItem {
  from_status: string | null;
  to_status: string;
  actor: UserBrief;
  comment: string | null;
  created_at: string;
}

export interface LeaveDetailResponse extends LeaveResponse {
  history: LeaveHistoryItem[];
}

export interface LeaveListResponse {
  items: LeaveResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  content: string;
  ref_type: string;
  ref_id: string;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
}
