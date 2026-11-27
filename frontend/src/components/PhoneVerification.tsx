import { useState } from "react";
import { useAuth } from "../auth";

export function PhoneVerification() {
  const auth = useAuth();
  const [phone, setPhone] = useState("+91");
  const [code, setCode] = useState("");
  const [requested, setRequested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const requestCode = async () => {
    setBusy(true); setError("");
    try { await auth.startPhoneVerification(phone.trim(), "case-recaptcha"); setRequested(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not send code"); }
    finally { setBusy(false); }
  };

  const confirm = async () => {
    setBusy(true); setError("");
    try { await auth.completePhoneVerification(code); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Code could not be verified"); }
    finally { setBusy(false); }
  };

  if (auth.user?.phoneNumber) return <p className="verified-phone">Phone verified: {auth.user.phoneNumber}</p>;
  return <div className="phone-verify">
    <strong>Verify your mobile number</strong>
    <p>This protects the case record and gives us a way to reach you about your report.</p>
    <label>Mobile number, with country code<input type="tel" value={phone}
      onChange={(event) => setPhone(event.target.value)} disabled={requested || busy} /></label>
    <div id="case-recaptcha" />
    {!requested ? <button type="button" className="button button--secondary" disabled={busy} onClick={() => void requestCode()}>Send code</button> : <>
      <label>Code from SMS<input inputMode="numeric" value={code} onChange={(event) => setCode(event.target.value)} /></label>
      <button type="button" className="button button--secondary" disabled={busy || code.trim().length < 4}
        onClick={() => void confirm()}>Verify code</button>
    </>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </div>;
}
