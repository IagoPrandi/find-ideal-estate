import { TriangleAlert } from "lucide-react";

const getConfiguredFormUrl = () => String(import.meta.env.VITE_FORM_URL || "").trim();

type FeedbackFormButtonProps = {
  formUrl?: string;
};

export function FeedbackFormButton({ formUrl = getConfiguredFormUrl() }: FeedbackFormButtonProps) {
  const normalizedUrl = formUrl.trim();
  const className = `feedback-form-button ${normalizedUrl ? "" : "feedback-form-button--disabled"}`.trim();

  if (!normalizedUrl) {
    return (
      <button
        type="button"
        className={className}
        aria-disabled="true"
        aria-label="Formulário em breve"
        title="Formulário em breve"
        disabled
        data-testid="feedback-form-button"
      >
        <TriangleAlert className="h-4 w-4" />
      </button>
    );
  }

  return (
    <a
      className={className}
      href={normalizedUrl}
      target="_blank"
      rel="noreferrer"
      aria-label="Abrir formulário"
      title="Abrir formulário"
      data-testid="feedback-form-button"
    >
      <TriangleAlert className="h-4 w-4" />
    </a>
  );
}
