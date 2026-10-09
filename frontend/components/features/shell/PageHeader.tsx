interface PageHeaderProps {
  title: string;
  description: string;
}

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <div className="mb-6">
      <h1 className="font-heading text-32 font-bold text-ink">{title}</h1>
      <p className="mt-1 text-15 text-body">{description}</p>
    </div>
  );
}
