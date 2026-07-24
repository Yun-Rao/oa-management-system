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
