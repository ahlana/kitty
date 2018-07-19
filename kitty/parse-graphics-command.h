#pragma once

static inline void
parse_graphics_code(Screen *screen, PyObject UNUSED *dump_callback) {
    unsigned int pos = 1;
    enum PARSER_STATES { KEY, EQUAL, UINT, INT, FLAG, AFTER_VALUE , PAYLOAD };
    enum PARSER_STATES state = KEY, value_state = FLAG;
    static GraphicsCommand g;
    unsigned int i, code;
    uint64_t lcode;
    bool is_negative;
    memset(&g, 0, sizeof(g));
    size_t sz;
    static uint8_t payload[4096];
    
    enum KEYS {
        action='a',
delete_action='d',
transmission_type='t',
compressed='o',
format='f',
more='m',
id='i',
width='w',
height='h',
x_offset='x',
y_offset='y',
data_height='v',
data_width='s',
data_sz='S',
data_offset='O',
num_cells='c',
num_lines='r',
cell_x_offset='X',
cell_y_offset='Y',
z_index='z'
    };
    
    enum KEYS key = 'a';

    while (pos < screen->parser_buf_pos) {
        switch(state) {
            case KEY:
                key = screen->parser_buf[pos++];
                state = EQUAL;
                switch(key) {
                    case action: value_state = FLAG; break;        
case delete_action: value_state = FLAG; break;        
case transmission_type: value_state = FLAG; break;        
case compressed: value_state = FLAG; break;        
case format: value_state = UINT; break;        
case more: value_state = UINT; break;        
case id: value_state = UINT; break;        
case width: value_state = UINT; break;        
case height: value_state = UINT; break;        
case x_offset: value_state = UINT; break;        
case y_offset: value_state = UINT; break;        
case data_height: value_state = UINT; break;        
case data_width: value_state = UINT; break;        
case data_sz: value_state = UINT; break;        
case data_offset: value_state = UINT; break;        
case num_cells: value_state = UINT; break;        
case num_lines: value_state = UINT; break;        
case cell_x_offset: value_state = UINT; break;        
case cell_y_offset: value_state = UINT; break;        
case z_index: value_state = INT; break;
                    default:
                        REPORT_ERROR("Malformed GraphicsCommand control block, invalid key character: 0x%x", key);
                        return;
                }
                break;

            case EQUAL:
                if (screen->parser_buf[pos++] != '=') {
                    REPORT_ERROR("Malformed GraphicsCommand control block, no = after key, found: 0x%x instead", screen->parser_buf[pos-1]);
                    return;
                }
                state = value_state;
                break;

            case FLAG:
                switch(key) {
                    
            case action: {
                g.action = screen->parser_buf[pos++] & 0xff;
                if (g.action != 'q' && g.action != 't' && g.action != 'p' && g.action != 'T' && g.action != 'd') {
                    REPORT_ERROR("Malformed GraphicsCommand control block, unknown flag value for action: 0x%x", g.action);
                    return;
                };
            }
            break;
                

            case delete_action: {
                g.delete_action = screen->parser_buf[pos++] & 0xff;
                if (g.delete_action != 'A' && g.delete_action != 'q' && g.delete_action != 'x' && g.delete_action != 'Y' && g.delete_action != 'z' && g.delete_action != 'a' && g.delete_action != 'Z' && g.delete_action != 'p' && g.delete_action != 'Q' && g.delete_action != 'c' && g.delete_action != 'P' && g.delete_action != 'y' && g.delete_action != 'C' && g.delete_action != 'i' && g.delete_action != 'X' && g.delete_action != 'I') {
                    REPORT_ERROR("Malformed GraphicsCommand control block, unknown flag value for delete_action: 0x%x", g.delete_action);
                    return;
                };
            }
            break;
                

            case transmission_type: {
                g.transmission_type = screen->parser_buf[pos++] & 0xff;
                if (g.transmission_type != 't' && g.transmission_type != 'f' && g.transmission_type != 's' && g.transmission_type != 'd') {
                    REPORT_ERROR("Malformed GraphicsCommand control block, unknown flag value for transmission_type: 0x%x", g.transmission_type);
                    return;
                };
            }
            break;
                

            case compressed: {
                g.compressed = screen->parser_buf[pos++] & 0xff;
                if (g.compressed != 'z') {
                    REPORT_ERROR("Malformed GraphicsCommand control block, unknown flag value for compressed: 0x%x", g.compressed);
                    return;
                };
            }
            break;
        
                    default:
                        break;
                }
                state = AFTER_VALUE;
                break;

            case INT:
#define READ_UINT \
                for (i = pos; i < MIN(screen->parser_buf_pos, pos + 10); i++) { \
                    if (screen->parser_buf[i] < '0' || screen->parser_buf[i] > '9') break; \
                } \
                if (i == pos) { REPORT_ERROR("Malformed GraphicsCommand control block, expecting an integer value for key: %c", key & 0xFF); return; } \
                lcode = utoi(screen->parser_buf + pos, i - pos); pos = i; \
                if (lcode > UINT32_MAX) { REPORT_ERROR("Malformed GraphicsCommand control block, number is too large"); return; } \
                code = lcode;

                is_negative = false;
                if(screen->parser_buf[pos] == '-') { is_negative = true; pos++; }
#define I(x) case x: g.x = is_negative ? 0 - (int32_t)code : (int32_t)code; break
                READ_UINT;
                switch(key) {
                    I(z_index);
                    default: break;
                }
                state = AFTER_VALUE;
                break;
#undef I
            case UINT:
                READ_UINT;
#define U(x) case x: g.x = code; break
                switch(key) {
                    U(format); U(more); U(id); U(width); U(height); U(x_offset); U(y_offset); U(data_height); U(data_width); U(data_sz); U(data_offset); U(num_cells); U(num_lines); U(cell_x_offset); U(cell_y_offset);
                    default: break;
                }
                state = AFTER_VALUE;
                break;
#undef U
#undef READ_UINT

            case AFTER_VALUE:
                switch (screen->parser_buf[pos++]) {
                    default:
                        REPORT_ERROR("Malformed GraphicsCommand control block, expecting a comma or semi-colon after a value, found: 0x%x",
                                     screen->parser_buf[pos - 1]);
                        return;
                    case ',':
                        state = KEY;
                        break;
                    case ';': state = PAYLOAD; break;
                }
                break;

            
            case PAYLOAD: {
                sz = screen->parser_buf_pos - pos;
                const char *err = base64_decode(screen->parser_buf + pos, sz, payload, sizeof(payload), &g.payload_sz);
                if (err != NULL) { REPORT_ERROR("Failed to parse GraphicsCommand command payload with error: %s", err); return; }
                pos = screen->parser_buf_pos;
                }
                break;
        

        } // end switch
    } // end while

    switch(state) {
        case EQUAL:
            REPORT_ERROR("Malformed GraphicsCommand control block, no = after key"); return;
        case INT:
        case UINT:
            REPORT_ERROR("Malformed GraphicsCommand control block, expecting an integer value"); return;
        case FLAG:
            REPORT_ERROR("Malformed GraphicsCommand control block, expecting a flag value"); return;
        default:
            break;
    }

    REPORT_VA_COMMAND("s {sc sc sc sc sI sI sI sI sI sI sI sI sI sI sI sI sI sI sI si sI} y#", "graphics_command",
"action", g.action, "delete_action", g.delete_action, "transmission_type", g.transmission_type, "compressed", g.compressed,
     "format", (unsigned int)g.format, "more", (unsigned int)g.more, "id", (unsigned int)g.id, "width", (unsigned int)g.width, "height", (unsigned int)g.height, "x_offset", (unsigned int)g.x_offset, "y_offset", (unsigned int)g.y_offset, "data_height", (unsigned int)g.data_height, "data_width", (unsigned int)g.data_width, "data_sz", (unsigned int)g.data_sz, "data_offset", (unsigned int)g.data_offset, "num_cells", (unsigned int)g.num_cells, "num_lines", (unsigned int)g.num_lines, "cell_x_offset", (unsigned int)g.cell_x_offset, "cell_y_offset", (unsigned int)g.cell_y_offset,
     "z_index", (int)g.z_index
, "payload_sz", g.payload_sz, payload, g.payload_sz
);

    screen_handle_graphics_command(screen, &g, payload);
}
    
