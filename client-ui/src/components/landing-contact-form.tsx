"use client";

import { FormEvent, useMemo, useState } from "react";

const CONTACT_EMAIL = "connor@stimpact.ai";

export function LandingContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [message, setMessage] = useState("");

  const isReady = useMemo(() => {
    return name.trim() && email.trim() && message.trim();
  }, [email, message, name]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const subject = `Stimpact.ai contact form: ${name.trim()}`;
    const lines = [
      `Name: ${name.trim()}`,
      `Email: ${email.trim()}`,
      `Company: ${company.trim() || "Not provided"}`,
      "",
      message.trim(),
    ];

    const mailtoUrl = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join("\n"))}`;
    window.location.href = mailtoUrl;
  }

  return (
    <form className="landing-contact-form" onSubmit={handleSubmit}>
      <div className="landing-contact-grid">
        <label className="landing-contact-field">
          <span>Name</span>
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Your name"
            required
          />
        </label>

        <label className="landing-contact-field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
            required
          />
        </label>
      </div>

      <label className="landing-contact-field">
        <span>Company</span>
        <input
          type="text"
          value={company}
          onChange={(event) => setCompany(event.target.value)}
          placeholder="Company or team"
        />
      </label>

      <label className="landing-contact-field">
        <span>How can we help?</span>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Tell us about your stack, incident workflow, or what you want to automate."
          rows={6}
          required
        />
      </label>

      <div className="landing-contact-actions">
        <p className="text-sm leading-7 text-white/56">
          Messages go directly to <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
        <button
          type="submit"
          className="landing-button-primary inline-flex items-center justify-center rounded-full px-6 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          disabled={!isReady}
        >
          Send message
        </button>
      </div>
    </form>
  );
}
