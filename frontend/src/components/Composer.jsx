import { useState } from 'react';

export function Composer({ disabled, onSubmit }) {
  const [draft, setDraft] = useState('');

  const submit = (event) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question || disabled) return;
    setDraft('');
    onSubmit(question);
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        value={draft}
        placeholder="Ask something about your documents…"
        rows={2}
        disabled={disabled}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) submit(event);
        }}
      />
      <button type="submit" disabled={disabled || draft.trim().length === 0}>
        Send
      </button>
    </form>
  );
}
