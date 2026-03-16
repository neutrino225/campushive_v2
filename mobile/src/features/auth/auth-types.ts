export type AuthUser = {
  id: number;
  username: string;
  email: string;
  role: string;
  created_at: string;
  updated_at: string;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export type LoginPayload = {
  username: string;
  password: string;
};

export type SignupPayload = {
  username: string;
  email: string;
  password: string;
};
