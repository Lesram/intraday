import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const { login } = vi.hoisted(() => ({ login: vi.fn() }));

vi.mock('@/hooks/useAuth', () => ({
  useLogin: () => ({ mutate: login, isPending: false }),
}));

async function renderLogin(dev = false, bypass = 'false') {
  vi.stubEnv('DEV', dev);
  vi.stubEnv('VITE_DEV_BYPASS_AUTH', bypass);
  const { default: LoginPage } = await import('./LoginPage');
  return render(
    <StrictMode>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </StrictMode>,
  );
}

function submit(username: string, password: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Username or email' }), {
    target: { value: username },
  });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
}

describe('LoginPage access contract', () => {
  beforeEach(() => {
    vi.resetModules();
    login.mockReset();
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      throw new Error('Network access is forbidden in login tests');
    });
    vi.spyOn(XMLHttpRequest.prototype, 'send').mockImplementation(() => {
      throw new Error('Network access is forbidden in login tests');
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('does not automatically submit in production even with the bypass flag enabled', async () => {
    await renderLogin(false, 'true');
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeEnabled();
    expect(login).not.toHaveBeenCalled();
  });

  it('does not automatically submit in development without explicit opt-in', async () => {
    await renderLogin(true, 'false');
    expect(login).not.toHaveBeenCalled();
  });

  it('retains the explicit development opt-in and only attempts once under StrictMode', async () => {
    await renderLogin(true, 'true');
    expect(login).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['plain username', '  paper_operator  ', 'paper_operator'],
    ['email', '  Operator@example.test  ', 'Operator@example.test'],
  ])('submits a trimmed %s without changing the password', async (_, entered, expected) => {
    await renderLogin();
    expect(login).not.toHaveBeenCalled();
    const password = '  Sample-passphrase  ';
    submit(entered, password);
    await waitFor(() => expect(login).toHaveBeenCalledExactlyOnceWith({ username: expected, password }));
  });

  it.each(['', '   '])('rejects an empty or whitespace-only username (%j)', async (username) => {
    await renderLogin();
    submit(username, 'Sample-passphrase');
    expect(await screen.findByText('Please enter your username or email!')).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it.each([
    ['', 'Please enter your password!'],
    ['short', 'Password must be at least 6 characters!'],
  ])('preserves existing password validation (%j)', async (password, error) => {
    await renderLogin();
    submit('paper_operator', password);
    expect(await screen.findByText(error)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it('provides honest recovery guidance without a dead recovery link', async () => {
    await renderLogin();
    expect(screen.getByText(/Password recovery is currently unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /forgot password|recovery/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sign up' })).toHaveAttribute('href', '/register');
  });
});
