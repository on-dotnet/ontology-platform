import java.io.File;
import java.util.Arrays;
import java.util.Optional;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.formats.TurtleDocumentFormat;
import org.semanticweb.owlapi.io.FileDocumentSource;
import org.semanticweb.owlapi.io.FileDocumentTarget;
import org.semanticweb.owlapi.io.RDFParserMetaData;
import org.semanticweb.owlapi.model.MissingImportHandlingStrategy;
import org.semanticweb.owlapi.model.OWLDocumentFormat;
import org.semanticweb.owlapi.model.OWLOntology;
import org.semanticweb.owlapi.model.OWLOntologyLoaderConfiguration;
import org.semanticweb.owlapi.model.OWLOntologyManager;

/**
 * Loads every Turtle file of a directory with OWL API, the way Protégé opens it, and saves it
 * back as Turtle. Prints one tab-separated line per file: RESULT, name, ok or error, the number
 * of triples OWL API could not parse, and a message. Run without network access: imports are
 * never fetched.
 */
public class RoundTrip {
  public static void main(String[] args) throws Exception {
    File inDir = new File(args[0]);
    File outDir = new File(args[1]);
    outDir.mkdirs();
    File[] files = inDir.listFiles((dir, name) -> name.endsWith(".ttl"));
    if (files == null) {
      throw new IllegalArgumentException("not a directory: " + inDir);
    }
    Arrays.sort(files);
    for (File file : files) {
      System.out.println(roundTrip(file, new File(outDir, file.getName())));
    }
  }

  private static String roundTrip(File file, File target) {
    OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
    OWLOntologyLoaderConfiguration config = new OWLOntologyLoaderConfiguration()
        .setMissingImportHandlingStrategy(MissingImportHandlingStrategy.SILENT);
    try {
      OWLOntology ontology =
          manager.loadOntologyFromOntologyDocument(new FileDocumentSource(file), config);
      OWLDocumentFormat source = manager.getOntologyFormat(ontology);
      int unparsed = unparsedTriples(source);
      TurtleDocumentFormat turtle = new TurtleDocumentFormat();
      if (source.isPrefixOWLOntologyFormat()) {
        turtle.copyPrefixesFrom(source.asPrefixOWLOntologyFormat());
      }
      manager.saveOntology(ontology, turtle, new FileDocumentTarget(target));
      return String.join("\t", "RESULT", file.getName(), "ok", Integer.toString(unparsed),
          ontology.getAxiomCount() + " axioms");
    } catch (Exception e) {
      String message = String.valueOf(e.getMessage()).replaceAll("\\s+", " ");
      return String.join("\t", "RESULT", file.getName(), "error", "0",
          e.getClass().getSimpleName() + ": " + message);
    }
  }

  private static int unparsedTriples(OWLDocumentFormat format) throws Exception {
    // OWL API 4 returns its own Optional type here; unwrap either kind.
    Object meta = format.getClass().getMethod("getOntologyLoaderMetaData").invoke(format);
    if (meta instanceof Optional) {
      meta = ((Optional<?>) meta).orElse(null);
    } else if (meta != null && meta.getClass().getName().startsWith("com.google.common.base.")) {
      meta = meta.getClass().getMethod("orNull").invoke(meta);
    }
    if (meta instanceof RDFParserMetaData) {
      return ((RDFParserMetaData) meta).getUnparsedTriples().size();
    }
    return 0;
  }
}
