import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { z } from "zod";

import { Input, Label } from "@/components/ui/Input";
import { Logomark } from "@/components/ui/Logomark";
import { supabase } from "@/lib/supabase";
import { cn } from "@/lib/cn";
import { useAuth } from "@/store/auth";
import { useAuthModal, type AuthModalMode } from "@/store/authModal";

const CONFIG_ERROR =
  "Supabase is not configured — create frontend/.env with VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.";

function friendlyAuthError(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("invalid login credentials")) {
    return "Wrong email or password. Try again.";
  }
  if (normalized.includes("already been registered") || normalized.includes("user already")) {
    return "That email is already registered — try logging in instead.";
  }
  if (normalized.includes("email not confirmed")) {
    return "Please confirm your email first — check your inbox.";
  }
  if (normalized.includes("rate limit") || normalized.includes("too many")) {
    return "Too many attempts — wait a moment and try again.";
  }
  if (normalized.includes("password should be at least")) {
    return "Password must be at least 6 characters.";
  }
  return message;
}

const emailSchema = z.string().email("Enter a valid email address");
const passwordSchema = z.string().min(6, "Use at least 6 characters");

const loginSchema = z.object({ email: emailSchema, password: passwordSchema });
type LoginValues = z.infer<typeof loginSchema>;

const signupSchema = z
  .object({ email: emailSchema, password: passwordSchema, confirm: z.string() })
  .refine((values) => values.confirm === values.password, {
    message: "Passwords do not match",
    path: ["confirm"],
  });
type SignupValues = z.infer<typeof signupSchema>;

const resetSchema = z.object({ email: emailSchema });
type ResetValues = z.infer<typeof resetSchema>;

const updatePasswordSchema = z
  .object({ password: passwordSchema, confirm: z.string() })
  .refine((values) => values.confirm === values.password, {
    message: "Passwords do not match",
    path: ["confirm"],
  });
type UpdatePasswordValues = z.infer<typeof updatePasswordSchema>;

const MODE_META: Record<AuthModalMode, { title: string; subtitle: string }> = {
  login: { title: "Welcome back", subtitle: "Your money, five pillars, one command center." },
  signup: { title: "Create your account", subtitle: "Your money, five pillars, one command center." },
  reset: { title: "Reset your password", subtitle: "We'll email you a reset link." },
  updatePassword: { title: "Choose a new password", subtitle: "You arrived here via your reset link." },
};

function FieldError({ message }: { message: string | undefined }) {
  if (!message) return null;
  return <p className="mt-1.5 text-xs text-danger">{message}</p>;
}

function SubmitButton({ label, busy }: { label: string; busy: boolean }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-60"
    >
      {busy ? "Working…" : label}
    </button>
  );
}

interface FormProps {
  onServerError: (message: string) => void;
}

function LoginForm({ onServerError, onForgotPassword }: FormProps & { onForgotPassword: () => void }) {
  const { register, handleSubmit, formState } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (values: LoginValues) => {
    if (!supabase) {
      onServerError(CONFIG_ERROR);
      return;
    }
    const { error } = await supabase.auth.signInWithPassword({
      email: values.email,
      password: values.password,
    });
    if (error) onServerError(friendlyAuthError(error.message));
    // Success: the auth state listener flips the store; the dialog routes on.
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
      <div>
        <Label htmlFor="login-email">Email</Label>
        <Input
          id="login-email"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
          {...register("email")}
        />
        <FieldError message={formState.errors.email?.message} />
      </div>
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <Label htmlFor="login-password" className="mb-0">
            Password
          </Label>
          <button
            type="button"
            onClick={onForgotPassword}
            className="text-xs text-muted underline-offset-2 transition-colors hover:text-ink hover:underline"
          >
            Forgot password?
          </button>
        </div>
        <Input
          id="login-password"
          type="password"
          placeholder="••••••••"
          autoComplete="current-password"
          {...register("password")}
        />
        <FieldError message={formState.errors.password?.message} />
      </div>
      <SubmitButton label="Log in to FinGuru" busy={formState.isSubmitting} />
    </form>
  );
}

function SignupForm({ onServerError, onAccountCreated }: FormProps & { onAccountCreated: () => void }) {
  const { register, handleSubmit, formState } = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
  });

  const onSubmit = async (values: SignupValues) => {
    if (!supabase) {
      onServerError(CONFIG_ERROR);
      return;
    }
    const { data, error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
    });
    if (error) {
      onServerError(friendlyAuthError(error.message));
      return;
    }
    if (data.session) return; // Signed up and signed in: the dialog routes on.
    onAccountCreated(); // Email confirmation required: mirror the legacy flow.
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
      <div>
        <Label htmlFor="signup-email">Email</Label>
        <Input
          id="signup-email"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
          {...register("email")}
        />
        <FieldError message={formState.errors.email?.message} />
      </div>
      <div>
        <Label htmlFor="signup-password">Password</Label>
        <Input
          id="signup-password"
          type="password"
          placeholder="••••••••"
          autoComplete="new-password"
          {...register("password")}
        />
        <FieldError message={formState.errors.password?.message} />
      </div>
      <div>
        <Label htmlFor="signup-confirm">Confirm password</Label>
        <Input
          id="signup-confirm"
          type="password"
          placeholder="••••••••"
          autoComplete="new-password"
          {...register("confirm")}
        />
        <FieldError message={formState.errors.confirm?.message} />
      </div>
      <SubmitButton label="Create my account" busy={formState.isSubmitting} />
    </form>
  );
}

function ResetForm({ onServerError, onNotice }: FormProps & { onNotice: (message: string) => void }) {
  const { register, handleSubmit, formState } = useForm<ResetValues>({
    resolver: zodResolver(resetSchema),
  });

  const onSubmit = async (values: ResetValues) => {
    if (!supabase) {
      onServerError(CONFIG_ERROR);
      return;
    }
    const { error } = await supabase.auth.resetPasswordForEmail(values.email, {
      redirectTo: `${window.location.origin}/`,
    });
    if (error) {
      onServerError(friendlyAuthError(error.message));
      return;
    }
    onNotice("If that email is registered, a reset link is on its way.");
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
      <div>
        <Label htmlFor="reset-email">Email</Label>
        <Input
          id="reset-email"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
          {...register("email")}
        />
        <FieldError message={formState.errors.email?.message} />
      </div>
      <SubmitButton label="Send reset link" busy={formState.isSubmitting} />
    </form>
  );
}

function UpdatePasswordForm({ onServerError, onDone }: FormProps & { onDone: () => void }) {
  const clearRecovery = useAuth((state) => state.clearRecovery);
  const { register, handleSubmit, formState } = useForm<UpdatePasswordValues>({
    resolver: zodResolver(updatePasswordSchema),
  });

  const onSubmit = async (values: UpdatePasswordValues) => {
    if (!supabase) {
      onServerError(CONFIG_ERROR);
      return;
    }
    const { error } = await supabase.auth.updateUser({ password: values.password });
    if (error) {
      onServerError(friendlyAuthError(error.message));
      return;
    }
    clearRecovery();
    onDone();
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
      <div>
        <Label htmlFor="update-password">New password</Label>
        <Input
          id="update-password"
          type="password"
          placeholder="••••••••"
          autoComplete="new-password"
          {...register("password")}
        />
        <FieldError message={formState.errors.password?.message} />
      </div>
      <div>
        <Label htmlFor="update-confirm">Confirm new password</Label>
        <Input
          id="update-confirm"
          type="password"
          placeholder="••••••••"
          autoComplete="new-password"
          {...register("confirm")}
        />
        <FieldError message={formState.errors.confirm?.message} />
      </div>
      <SubmitButton label="Update password" busy={formState.isSubmitting} />
    </form>
  );
}

const TOGGLE_LABELS: Record<"login" | "signup", string> = {
  login: "Log in",
  signup: "Create account",
};

export function AuthModal() {
  const open = useAuthModal((state) => state.open);
  const recoveryPending = useAuth((state) => state.recoveryPending);
  const openModal = useAuthModal((state) => state.openModal);

  useEffect(() => {
    if (recoveryPending) openModal("updatePassword");
  }, [recoveryPending, openModal]);

  if (!open) return null;
  return <AuthModalDialog />;
}

function AuthModalDialog() {
  const mode = useAuthModal((state) => state.mode);
  const closeModal = useAuthModal((state) => state.closeModal);
  const setMode = useAuthModal((state) => state.setMode);
  const user = useAuth((state) => state.user);
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeModal();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeModal]);

  useEffect(() => {
    if (user && mode !== "updatePassword") {
      closeModal();
      navigate("/track", { replace: true });
    }
  }, [user, mode, closeModal, navigate]);

  const clearMessages = () => {
    setServerError(null);
    setNotice(null);
  };

  const switchMode = (next: AuthModalMode) => {
    setMode(next);
    clearMessages();
  };

  const meta = MODE_META[mode];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={closeModal}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={meta.title}
        className="relative w-full max-w-md rounded-xl border border-edge bg-surface p-6 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          aria-label="Close"
          onClick={closeModal}
          className="absolute right-4 top-4 rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-ink"
        >
          <X className="size-4" />
        </button>

        <Logomark className="size-9 text-base" />
        <h2 className="mt-4 text-xl font-semibold text-ink">{meta.title}</h2>
        <p className="mt-1 text-sm text-muted">{meta.subtitle}</p>

        {mode === "login" || mode === "signup" ? (
          <div className="mt-5 grid grid-cols-2 gap-1 rounded-lg bg-base p-1" role="tablist">
            {(Object.keys(TOGGLE_LABELS) as ("login" | "signup")[]).map((option) => (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={mode === option}
                onClick={() => switchMode(option)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  mode === option ? "bg-surface-hover text-ink" : "text-muted hover:text-ink",
                )}
              >
                {TOGGLE_LABELS[option]}
              </button>
            ))}
          </div>
        ) : null}

        {mode === "login" ? (
          <LoginForm
            onServerError={setServerError}
            onForgotPassword={() => switchMode("reset")}
          />
        ) : null}
        {mode === "signup" ? (
          <SignupForm
            onServerError={setServerError}
            onAccountCreated={() => {
              setMode("login");
              setNotice("Account created! Check your email to confirm, then log in.");
            }}
          />
        ) : null}
        {mode === "reset" ? (
          <ResetForm onServerError={setServerError} onNotice={setNotice} />
        ) : null}
        {mode === "updatePassword" ? (
          <UpdatePasswordForm onServerError={setServerError} onDone={() => navigate("/track")} />
        ) : null}

        {serverError ? (
          <p
            role="alert"
            className="mt-3 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger"
          >
            {serverError}
          </p>
        ) : null}
        {notice ? (
          <p
            role="status"
            className="mt-3 rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-xs text-accent"
          >
            {notice}
          </p>
        ) : null}

        {mode === "login" || mode === "signup" ? (
          <p className="mt-4 text-center text-xs text-muted">
            {mode === "login" ? "New to FinGuru? " : "Already have an account? "}
            <button
              type="button"
              onClick={() => switchMode(mode === "login" ? "signup" : "login")}
              className="font-medium text-accent underline-offset-2 hover:underline"
            >
              {TOGGLE_LABELS[mode === "login" ? "signup" : "login"]}
            </button>
          </p>
        ) : (
          <p className="mt-4 text-center text-xs text-muted">
            <button
              type="button"
              onClick={() => switchMode("login")}
              className="font-medium text-accent underline-offset-2 hover:underline"
            >
              Back to log in
            </button>
          </p>
        )}
      </div>
    </div>
  );
}
