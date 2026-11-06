export function accountErrors(username: string, password: string, register: boolean) {
  return {
    username: /^[a-zA-Z0-9_]{3,32}$/.test(username) ? '' : 'Use 3–32 letters, digits or underscores for your username.',
    password: password.length >= (register ? 15 : 1) && password.length <= 128 && !password.includes('\0')
      ? '' : register ? 'Use 15–128 characters for your password.' : 'Enter your password (up to 128 characters).',
  };
}
