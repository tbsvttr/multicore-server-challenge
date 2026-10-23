// Emit every actual generated statement as PostgreSQL PREPARE commands.
// This is a review/EXPLAIN helper, not a server or benchmark.
import sql;
import std;

fn main() {
    for i in STATEMENTS {
        var out: u8[>..] = [];
        format(out, "PREPARE s", i);
        let types = statement_types(i);
        if types.len > 0 {
            out.push('(');
            for t, k in types {
                if k > 0 { out.push(','); }
                out.append(if t == 'i' { "bigint" } else if t == 'I' { "bigint[]" } else if t == 'a' { "text[]" } else { "text" });
            }
            out.push(')');
        }
        out.append(" AS ");
        statement(out, i);
        out.push(';');
        print(out);
    }
}
