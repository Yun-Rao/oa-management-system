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

export type ExpenseType = "travel" | "office" | "entertainment" | "transport" | "other";
export type ExpenseStatus = "pending_l1" | "pending_l2" | "approved" | "rejected" | "cancelled";

export interface ExpenseItem {
  id: string;
  type: string;
  amount: string;
  reason: string;
  status: string;
  applicant: UserBrief;
  approver: UserBrief | null;
  created_at: string;
  updated_at: string;
}

export interface ExpenseHistoryItem {
  from_status: string | null;
  to_status: string;
  actor: UserBrief;
  comment: string | null;
  created_at: string;
}

export interface ExpenseAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface ExpenseDetail extends ExpenseItem {
  history: ExpenseHistoryItem[];
  attachments: ExpenseAttachment[];
}

export interface ExpenseListResponse {
  items: ExpenseItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeaveStatItem {
  department_id: string;
  department_name: string;
  request_count: number;
  total_days: number;
}

export interface ExpenseStatItem {
  department_id: string;
  department_name: string;
  request_count: number;
  total_amount: string;
}

export interface ApprovalDurationItem {
  category: string;
  completed_count: number;
  avg_hours: number | null;
}

export interface DashboardSummary {
  month: string;
  leave_stats: LeaveStatItem[];
  expense_stats: ExpenseStatItem[];
  approval_durations: ApprovalDurationItem[];
}
