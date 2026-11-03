import { useId, useState } from 'react';
import type { SubmitEvent } from 'react';
import type { Credentials } from '../api/index.ts';

export function AuthForm({ disabled, onSubmit, recoveryUsername, initialRegister = false }: {
  disabled: boolean; onSubmit: (credentials: Credentials, register: boolean) => void;
  recoveryUsername?: string;
  initialRegister?: boolean;
}) {
  const [registerMode, setRegister] = useState(initialRegister);
  const hint = useId();
  const [validation, setValidation] = useState('');
  const register = !recoveryUsername && registerMode;
  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const credentials = { username: recoveryUsername ?? String(data.get('username')), password: String(data.get('password')) };
    form.reset();
    onSubmit(credentials, register);
  }
  return <section className="geo-auth" aria-labelledby="account-title">
    <span className="geo-label">{recoveryUsername ? 'Account recovery' : register ? 'Your first campaign awaits' : 'Welcome to Geopolitics'}</span>
    <h2 id="account-title">{recoveryUsername ? 'Log in to recover the saved request' : register ? 'Create an account' : 'Log in'}</h2>
    <form onSubmit={submit} onInput={() => setValidation('')} onInvalidCapture={() => setValidation('Check the username and password requirements before continuing.')}>
      <fieldset disabled={disabled}>
        <legend className="geo-visually-hidden">{register ? 'Register and log in' : 'Account details'}</legend>
        <label>Username <input name="username" required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_]+" autoComplete="username"
          defaultValue={recoveryUsername} readOnly={!!recoveryUsername} aria-describedby={register ? hint : undefined} /></label>
        <label>Password <input name="password" type="password" required minLength={register ? 15 : 1} maxLength={128}
          aria-describedby={register ? hint : undefined} autoComplete={register ? 'new-password' : 'current-password'} /></label>
        {register && <p id={hint} className="geo-help">Use 3–32 letters, digits or underscores for your username and 15–128 characters for your password.</p>}
        <button className="geo-screen-primary" type="submit">{register ? 'Register and log in' : 'Log in'}</button>
        {!recoveryUsername && <button className="geo-screen-link" type="button" onClick={() => { if (!disabled) setRegister(!register); }}>{register ? 'Use an existing account' : 'Create an account'}</button>}
      </fieldset>
      {validation && <p role="alert">{validation}</p>}
    </form>
  </section>;
}
