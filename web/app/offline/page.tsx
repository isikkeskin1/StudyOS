export default function OfflinePage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
        background: "#080b10",
        color: "#f4f7fb",
        fontFamily: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <section
        style={{
          width: "min(520px, 100%)",
          padding: 28,
          border: "1px solid #202b38",
          borderRadius: 18,
          background: "#0e131b",
          boxShadow: "0 22px 70px rgba(0,0,0,.28)",
        }}
      >
        <div
          style={{
            width: 42,
            height: 42,
            display: "grid",
            placeItems: "center",
            borderRadius: 12,
            background: "#9ff5c8",
            color: "#07110c",
            fontWeight: 900,
          }}
        >
          S
        </div>
        <p
          style={{
            margin: "22px 0 8px",
            color: "#9ff5c8",
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: ".15em",
            textTransform: "uppercase",
          }}
        >
          Offline mode
        </p>
        <h1 style={{ margin: "0 0 10px", fontSize: 30, letterSpacing: "-.04em" }}>
          StudyOS is offline
        </h1>
        <p style={{ margin: 0, color: "#8794a4", fontSize: 13, lineHeight: 1.65 }}>
          The app shell is available, but live plans, grades, reviews, and focus state stay network-only so
          StudyOS never presents stale academic data as current.
        </p>
        <a
          href="/"
          style={{
            display: "inline-flex",
            alignItems: "center",
            minHeight: 40,
            marginTop: 22,
            padding: "0 14px",
            borderRadius: 10,
            background: "#9ff5c8",
            color: "#07110c",
            fontSize: 12,
            fontWeight: 800,
            textDecoration: "none",
          }}
        >
          Try reconnecting
        </a>
      </section>
    </main>
  );
}
