import { Path, UseFormSetError } from 'react-hook-form';
import { z } from 'zod';

const usernameSchema = z
  .string()
  .trim()
  .min(3, 'Username must be at least 3 characters')
  .max(50, 'Username must be 50 characters or fewer')
  .regex(/^[a-zA-Z0-9_]+$/, 'Username must contain only letters, numbers, and underscores');

const passwordSchema = z
  .string()
  .min(8, 'Password must be at least 8 characters long')
  .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
  .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
  .regex(/\d/, 'Password must contain at least one digit');

export const loginSchema = z.object({
  username: z.string().trim().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
});

export const signupSchema = z
  .object({
    username: usernameSchema,
    email: z.string().trim().email('Enter a valid email address'),
    password: passwordSchema,
    confirmPassword: z.string().min(1, 'Confirm your password'),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  });

export type LoginFormValues = z.infer<typeof loginSchema>;
export type SignupFormValues = z.infer<typeof signupSchema>;

export function applyZodIssues<T extends Record<string, unknown>>(
  setError: UseFormSetError<T>,
  issues: z.ZodIssue[],
) {
  for (const issue of issues) {
    const field = issue.path[0];
    if (typeof field === 'string') {
      setError(field as Path<T>, {
        type: 'manual',
        message: issue.message,
      });
    }
  }
}
