import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const authMocks = vi.hoisted(() => ({
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  updateUser: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signInWithPassword: authMocks.signInWithPassword,
      signUp: authMocks.signUp,
      resetPasswordForEmail: authMocks.resetPasswordForEmail,
      updateUser: authMocks.updateUser,
      signOut: authMocks.signOut,
      getSession: vi.fn(async () => ({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  },
}));

import { AuthModal } from "@/pages/landing/components/AuthModal";
import { LandingPage } from "@/pages/landing/LandingPage";
import { useAuthModal } from "@/store/authModal";

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
      <AuthModal />
    </MemoryRouter>,
  );
}

function openModal() {
  fireEvent.click(screen.getAllByRole("button", { name: "Enter FinGuru" })[0]);
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthModal.getState().closeModal();
});

describe("AuthModal", () => {
  it("opens from a hero CTA and toggles between login and signup", () => {
    renderLanding();
    openModal();

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.queryByLabelText("Confirm password")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Create account" }));
    expect(screen.getByLabelText("Confirm password")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create my account" })).toBeTruthy();
  });

  it("closes via the close affordance", () => {
    renderLanding();
    openModal();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows a friendly inline error when Supabase rejects the credentials", async () => {
    authMocks.signInWithPassword.mockResolvedValue({
      data: {},
      error: { message: "Invalid login credentials" },
    });
    renderLanding();
    openModal();

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "dev@finguru.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrongpass" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in to FinGuru" }));

    expect(await screen.findByText("Wrong email or password. Try again.")).toBeTruthy();
    expect(authMocks.signInWithPassword).toHaveBeenCalledWith({
      email: "dev@finguru.test",
      password: "wrongpass",
    });
  });

  it("rejects mismatched signup passwords inline without calling Supabase", async () => {
    renderLanding();
    openModal();
    fireEvent.click(screen.getByRole("tab", { name: "Create account" }));

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "dev@finguru.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret1" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "secret2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create my account" }));

    expect(await screen.findByText("Passwords do not match")).toBeTruthy();
    expect(authMocks.signUp).not.toHaveBeenCalled();
  });

  it("confirms account creation and switches to login when email confirmation is required", async () => {
    authMocks.signUp.mockResolvedValue({ data: { session: null, user: { id: "u1" } }, error: null });
    renderLanding();
    openModal();
    fireEvent.click(screen.getByRole("tab", { name: "Create account" }));

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@finguru.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret1" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "secret1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create my account" }));

    expect(await screen.findByText(/check your email to confirm/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Log in to FinGuru" })).toBeTruthy();
  });

  it("sends a reset email from the forgot-password view", async () => {
    authMocks.resetPasswordForEmail.mockResolvedValue({ data: {}, error: null });
    renderLanding();
    openModal();

    fireEvent.click(screen.getByRole("button", { name: "Forgot password?" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "dev@finguru.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    await waitFor(() =>
      expect(authMocks.resetPasswordForEmail).toHaveBeenCalledWith(
        "dev@finguru.test",
        expect.anything(),
      ),
    );
    expect(await screen.findByText(/reset link is on its way/i)).toBeTruthy();
  });
});
