type Props = {
  url?: string;
  text: string;
  className?: string;
};

export default function NewsHeadlineLink({ url, text, className = "news-headline" }: Props) {
  const trimmed = (url || "").trim();
  if (trimmed) {
    return (
      <a
        href={trimmed}
        target="_blank"
        rel="noopener noreferrer"
        className={`${className} news-headline-link`}
        title="기사 원문 (새 탭)"
      >
        {text}
      </a>
    );
  }
  return <div className={className}>{text}</div>;
}
