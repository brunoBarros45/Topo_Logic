export const URL = globalThis.URL;
export const URLSearchParams = globalThis.URLSearchParams;

export function domainToASCII(domain: string): string {
  if (!domain) return "";
  try {
    return new globalThis.URL(`http://${domain}`).hostname;
  } catch {
    return domain;
  }
}

export function domainToUnicode(domain: string): string {
  return domain;
}

const urlShim = {
  URL,
  URLSearchParams,
  domainToASCII,
  domainToUnicode,
};

export default urlShim;
