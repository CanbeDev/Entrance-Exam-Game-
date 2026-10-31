import { useState } from 'react';
import type { SubmitEvent } from 'react';
import type { Credentials } from '../api/index.ts';

export function AuthForm({ disabled, onSubmit, recoveryUsername }: {
  disabled: boolean; onSubmit: (credentials: Credentials, register: boolean) => void;
  recoveryUsername?: string;
}) {
  const [registerMode, setRegister] = useState(false);
  const register = !recoveryUsername && registerMode;
  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const credentials = { username: String(data.get('username')), password: String(data.get('password')) };
    form.reset();
    onSubmit(credentials, register);
  }
  return <section aria-labelledby="account-title">
    <h2 id="account-title">{recoveryUsername ? 'Log in to recover the saved request' : register ? 'Create an account' : 'Log in'}</h2>
    <form onSubmit={submit}>
      <fieldset disabled={disabled}>
        <legend>{register ? 'Register and log in' : 'Account details'}</legend>
        <label>Username <input name="username" required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_]+" autoComplete="username"
          defaultValue={recoveryUsername} readOnly={!!recoveryUsername} /></label>
        <label>Password <input name="password" type="password" required minLength={register ? 15 : 1} maxLength={128}
          autoComplete={register ? 'new-password' : 'current-password'} /></label>
        {register && <p>Use 3–32 letters, digits or underscores for your username and at least 15 characters for your password.</p>}
        <button type="submit">{register ? 'Register and log in' : 'Log in'}</button>
        {!recoveryUsername && <button type="button" onClick={() => setRegister(!register)}>{register ? 'Use an existing account' : 'Create an account'}</button>}
      </fieldset>
    </form>
  </section>;
}
