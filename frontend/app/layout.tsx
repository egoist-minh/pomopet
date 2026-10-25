import type { Metadata } from 'next';
import { Inter, JetBrains_Mono, Space_Grotesk } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' });
const jetbrainsMono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' });
const space = Space_Grotesk({ subsets: ['latin'], variable: '--font-space' });

export const metadata: Metadata = {
  title: 'PomoPet — AI Focus Companion',
  description: 'A tiny AI focus companion that lives on your desktop',
};

const productionContentSecurityPolicy =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' http://127.0.0.1:* http://localhost:* ws://localhost:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${jetbrainsMono.variable} ${space.variable} antialiased`}>
      <head>
        {process.env.NODE_ENV === 'production' ? (
          <meta
            httpEquiv="Content-Security-Policy"
            content={productionContentSecurityPolicy}
          />
        ) : null}
      </head>
      <body suppressHydrationWarning className="bg-transparent">{children}</body>
    </html>
  );
}
