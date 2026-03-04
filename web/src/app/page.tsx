import { getDecreeData } from "@/lib/data";
import { getUniqueStreets } from "@/lib/normalize";
import SearchApp from "@/components/SearchApp";

export default function Home() {
  // Load street list server-side for autocomplete
  const data = getDecreeData();
  const streets = getUniqueStreets(data.rules);
  const schoolCount = data.schools.length;
  const validFrom = data.metadata.valid_from;

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <header className="text-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Lokito
        </h1>
        <p className="text-lg text-gray-600">
          Do jaké základní školy vaše dítě spádově patří?
        </p>
        <p className="text-sm text-gray-400 mt-1">
          Praha 10 · {schoolCount} škol · platné od {validFrom}
        </p>
      </header>

      <SearchApp streets={streets} />

      <footer className="mt-12 text-center text-xs text-gray-400 space-y-1">
        <p>
          Data vychází ze spádové vyhlášky městské části Praha 10.
        </p>
        <p>
          Tento nástroj je informativní. Závazná je vždy platná vyhláška.
        </p>
      </footer>
    </main>
  );
}
