export const metadata = {
  title: "EconoDeal",
  description: "EconoDeal App Router",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
