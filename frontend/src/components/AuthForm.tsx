import { useId, useImperativeHandle, useState } from 'react';
import type { Ref, SubmitEvent } from 'react';
import type { Credentials } from '../api/index.ts';
import { accountErrors } from './auth-validation.ts';

export type AuthFormDisplay = { showLogin: () => void; showRegistration: () => void };

export function AuthForm({ disabled, onSubmit, recoveryUsername, initialRegister = false, registrationInvitation = false, displayRef }: {
  disabled: boolean; onSubmit: (credentials: Credentials, register: boolean) => void;
  recoveryUsername?: string;
  initialRegister?: boolean;
  registrationInvitation?: boolean;
  displayRef?: Ref<AuthFormDisplay>;
}) {
  const [registerMode, setRegister] = useState(initialRegister);
  const hint = useId();
  const [validation, setValidation] = useState({ username: '', password: '' });
  const register = !recoveryUsername && registerMode;
  useImperativeHandle(displayRef, () => ({
    showLogin: () => { if (!disabled && !recoveryUsername) setRegister(false); },
    showRegistration: () => { if (!disabled && !recoveryUsername) setRegister(true); },
  }), [disabled, recoveryUsername]);
  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const credentials = { username: recoveryUsername ?? String(data.get('username')), password: String(data.get('password')) };
    const errors = accountErrors(credentials.username, credentials.password, register);
    setValidation(errors);
    if (errors.username || errors.password) {
      form.querySelector<HTMLInputElement>(errors.username ? '[name="username"]' : '[name="password"]')?.focus();
      return;
    }
    form.reset();
    onSubmit(credentials, register);
  }
  return <section className="geo-auth" aria-labelledby="account-title">
    <span className="geo-label">{recoveryUsername ? 'Account recovery' : register ? 'Your first campaign awaits' : 'Welcome to Geopolitics'}</span>
    <h2 id="account-title">{recoveryUsername ? 'Log in to recover the saved request' : register ? 'Create an account' : 'Log in'}</h2>
    <form noValidate onSubmit={submit} onInput={() => setValidation({ username: '', password: '' })}>
      <fieldset disabled={disabled}>
        <legend className="geo-visually-hidden">{register ? 'Register and log in' : 'Account details'}</legend>
        <label>Username <input name="username" required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_]+" autoComplete="username"
          defaultValue={recoveryUsername} readOnly={!!recoveryUsername} aria-invalid={!!validation.username}
          aria-describedby={[register ? hint : '', validation.username ? `${hint}-username` : ''].filter(Boolean).join(' ') || undefined} /></label>
        {validation.username && <p id={`${hint}-username`} role="alert" className="geo-field-error">{validation.username}</p>}
        <label>Password <input name="password" type="password" required minLength={register ? 15 : 1} maxLength={128}
          aria-invalid={!!validation.password} aria-describedby={[register ? hint : '', validation.password ? `${hint}-password` : ''].filter(Boolean).join(' ') || undefined}
          autoComplete={register ? 'new-password' : 'current-password'} /></label>
        {validation.password && <p id={`${hint}-password`} role="alert" className="geo-field-error">{validation.password}</p>}
        {register && <p id={hint} className="geo-help">Use 3–32 letters, digits or underscores for your username and 15–128 characters for your password.</p>}
        <button className="geo-screen-primary" type="submit">{register ? 'Register and log in' : 'Log in'}</button>
        {registrationInvitation && !register && !recoveryUsername && <p className="geo-auth__invitation">New to Geopolitics?</p>}
        {!recoveryUsername && <button className="geo-screen-link" type="button" onClick={() => { if (!disabled) setRegister(!register); }}>{register ? 'Use an existing account' : 'Create an account'}</button>}
      </fieldset>
    </form>
  </section>;
}
